"""Shared per-stock analysis pipeline.

Both the Dashboard, Forward Outlook and Today's Playbook need the same
expensive computation per ticker. Extracting it here lets Streamlit's
@st.cache_data share results across pages: the first page that triggers
the work pays the cost, all subsequent pages get instant cache hits.

This module is allowed to import streamlit (for caching) but the heavy
lifting still lives in the streamlit-free `core/` package.

Enhancement toggles (GARCH, macro, regime-grade) are applied here so all
pages see consistent results. Each toggle creates its own cache key so
turning a toggle on/off doesn't invalidate the vanilla cache.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
from typing import Any

import streamlit as st

from core.backtest import backtest_all, trust_grade
from core.circuit_breaker import CircuitBreakerStatus, check_drawdown
from core.data import fetch_history
from core.earnings_proxy import detect as earnings_detect
from core.forecast import ensemble_forecast, naive_forecast
from core.forecast_weighted import RecencyWeights, recency_weighted_forecast
from core.fx import normalise_to_aud
from core.hold_window import upcoming_window
from core.macro import macro_blocks_go, macro_snapshot
from core.pipeline_cache import cache_status, load_cached, save_cached
from core.regime import detect_regime
from core.regime_grade import stratified_grade
from core.settings import Enhancements, all_off
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snapshot
from core.tickers import WATCHLIST
from core.volatility import VolatilityForecast, forecast_vol

# How many walk-forward folds the watchlist trust grade uses.
# 12 folds ≈ 3 years of quarterly tests — enough for a meaningful trust
# grade, ~40% faster than the previous 20. The Backtest Lab can override
# this for deeper analysis (its own UI exposes the cap).
WATCHLIST_MAX_FOLDS = 12

# Default number of parallel workers for analyse_all(). 4 is a comfortable
# fit on Streamlit Cloud's 1 GB free tier (4 × ~150 MB peak). Override via
# the parameter if running on more powerful hardware.
DEFAULT_PARALLEL_WORKERS = 4


@st.cache_data(ttl=3600, show_spinner=False)
def analyse_one(
    symbol: str,
    broker: str = "Stake",
    enh_label: str = "vanilla",
    enh_garch: bool = False,
    enh_macro: bool = False,
    enh_regime_grade: bool = False,
    enh_recency_weighted: bool = False,
    enh_drawdown_breaker: bool = False,
) -> dict[str, Any]:
    """Run the full per-stock pipeline. Cached for 1 hour, shared across pages.

    Toggles are passed as primitive booleans (not the Enhancements dataclass)
    because @st.cache_data hashes args and frozen dataclasses don't always
    play nicely with that. The bools become the cache key, so each toggle
    combination has its own cache slot.

    Three-tier caching:
      1. `@st.cache_data` (in-memory, this session, 1 hour)
      2. Disk pickle cache (`core/pipeline_cache.py`, survives sleeps + new
         sessions, 24 hour TTL)
      3. Recompute from scratch (the slow path: ~13 sec per stock)
    """
    enh = Enhancements(
        use_garch=enh_garch,
        use_macro_confirm=enh_macro,
        use_regime_grade=enh_regime_grade,
        use_recency_weighted=enh_recency_weighted,
        use_drawdown_breaker=enh_drawdown_breaker,
        label=enh_label,
    )

    t = next(x for x in WATCHLIST if x.symbol == symbol)

    # Tier 2: disk cache. Strips df to keep pickles small; we re-attach it
    # below from the parquet cache (which is itself ~40ms cheap).
    toggle_kwargs = {
        "enh_garch": enh_garch,
        "enh_macro": enh_macro,
        "enh_regime_grade": enh_regime_grade,
        "enh_recency_weighted": enh_recency_weighted,
        "enh_drawdown_breaker": enh_drawdown_breaker,
    }
    cached = load_cached(symbol, broker, toggle_kwargs)
    if cached is not None:
        try:
            df_native = fetch_history(symbol, years=20, adjusted=True)
            df = normalise_to_aud(df_native, t)
            cached["df"] = df
            cached["enhancements"] = enh
            return cached
        except Exception:  # noqa: BLE001
            # Re-fetch failed for some reason — fall through to full recompute.
            pass

    # Tier 3: full recompute.
    df_native = fetch_history(symbol, years=20, adjusted=True)
    df = normalise_to_aud(df_native, t)

    if len(df) < 252 * 5:
        return {
            "symbol": symbol,
            "name": t.name,
            "ticker": t,
            "error": "Less than 5 years of data.",
            "enhancements": enh,
        }

    # Use the most-recent ~3 years of quarterly folds for the live trust
    # grade. Keeps per-ticker run time manageable across the 21-stock
    # watchlist. The Backtest Lab can override max_folds for deeper history.
    bt = backtest_all(
        df, horizon_days=90, market=t.market,
        broker=broker, max_folds=WATCHLIST_MAX_FOLDS,
    )
    rg = detect_regime(df)

    # Trust grade: vanilla OR regime-stratified depending on toggle
    if enh.use_regime_grade:
        srg = stratified_grade(df, bt, rg.label, horizon_days=90)
        grade = srg.grade
        regime_grade_obj: Any = srg
    else:
        grade = trust_grade(bt)
        regime_grade_obj = None

    # Recency-weighted ensemble (toggle #4) reuses the bt results we just
    # computed - no extra fitting cost. Falls back to vanilla equal-weight
    # internally if there isn't enough fold data.
    recency_weights: RecencyWeights | None = None
    if enh.use_recency_weighted:
        fcast, recency_weights = recency_weighted_forecast(
            df, bt, horizon_days=90,
        )
    else:
        fcast = ensemble_forecast(df, horizon_days=90)
    naive = naive_forecast(df, horizon_days=90)
    snap = tech_snapshot(df)
    earn = earnings_detect(df)
    spot = float(df["close"].iloc[-1])
    stops = stops_suggest(df, hold_days=90, current_price=spot)
    hold = upcoming_window(df, current_month=datetime.today().month)

    # GARCH forecast - always computed cheaply when toggle on, used downstream
    vol: VolatilityForecast | None = None
    if enh.use_garch:
        vol = forecast_vol(df, horizon_days=90)

    naive_drift = ((float(naive.forecast_mean[-1]) / spot) - 1) * 100
    sig = decide(
        trust=grade, regime=rg, hold=hold, forecast=fcast,
        technicals=snap, earnings=earn, stops=stops,
        spot_price=spot, naive_baseline_drift_pct=naive_drift,
    )

    # Macro confirmation overlay - only blocks GO signals, never creates new ones
    macro = None
    if enh.use_macro_confirm:
        macro = macro_snapshot(t.market)
        if sig.state == "GO" and macro_blocks_go(macro):
            from core.signals import TradeSignal
            sig = TradeSignal(
                state="WAIT",
                confidence=sig.confidence * 0.5,
                headline=f"WAIT (macro override) - {macro.mood} cross-asset conditions.",
                reasons=[macro.interpretation, *sig.reasons],
            )

    # Drawdown circuit-breaker (toggle #5). Layers on AFTER macro because we
    # want both safety filters to be able to suppress a GO independently.
    breaker: CircuitBreakerStatus | None = None
    if enh.use_drawdown_breaker:
        breaker = check_drawdown(df)
        if breaker.triggered and sig.state == "GO":
            from core.signals import TradeSignal
            sig = TradeSignal(
                state="WAIT",
                confidence=sig.confidence * 0.5,
                headline=(
                    f"WAIT (drawdown breaker) - {breaker.drawdown_pct:.1f}% off "
                    f"{breaker.window_days}-day peak."
                ),
                reasons=[breaker.interpretation, *sig.reasons],
            )

    expected_pct = ((float(fcast.forecast_mean[-1]) / spot) - 1) * 100

    result = {
        "symbol": symbol,
        "name": t.name,
        "sector": t.sector,
        "market": t.market,
        "ticker": t,
        "df": df,
        "spot_aud": spot,
        "trust_grade": grade.grade,
        "trust_score": grade.score,
        "grade": grade,
        "regime": rg.label,
        "regime_obj": rg,
        "signal": sig.state,
        "signal_obj": sig,
        "signal_headline": sig.headline,
        "expected_90d_pct": expected_pct,
        "forecast": fcast,
        "naive": naive,
        "stops": stops,
        "hold": hold,
        "earnings": earn,
        "technicals": snap,
        "ensemble_directional_pct": bt["ensemble"].directional_accuracy_pct,
        "naive_directional_pct": bt["naive"].directional_accuracy_pct,
        "hold_window": hold.description if hold else "(no active window)",
        "enhancements": enh,
        "vol": vol,
        "macro": macro,
        "regime_grade_obj": regime_grade_obj,
        "backtest": bt,
        "recency_weights": recency_weights,
        "breaker": breaker,
    }

    # Tier 2 cache write. Best-effort; never blocks or crashes the page.
    try:
        save_cached(symbol, broker, toggle_kwargs, result)
    except Exception:  # noqa: BLE001
        pass

    return result


def _enh_kwargs(enh: Enhancements) -> dict[str, Any]:
    """Convert an Enhancements bundle into the kwarg dict analyse_one() takes.

    Uses `getattr` defensively for every field so a stale Enhancements object
    (e.g. one pickled before the v1.3 fields existed and rehydrated from
    session_state on a redeploy) doesn't crash the watchlist scan. Missing
    fields safely default to OFF.
    """
    return {
        "enh_label": getattr(enh, "label", None) or getattr(enh, "short_label", lambda: "vanilla")(),
        "enh_garch": bool(getattr(enh, "use_garch", False)),
        "enh_macro": bool(getattr(enh, "use_macro_confirm", False)),
        "enh_regime_grade": bool(getattr(enh, "use_regime_grade", False)),
        "enh_recency_weighted": bool(getattr(enh, "use_recency_weighted", False)),
        "enh_drawdown_breaker": bool(getattr(enh, "use_drawdown_breaker", False)),
    }


def is_watchlist_warm(broker: str = "Stake", enh: Enhancements | None = None) -> bool:
    """Cheap check: is the watchlist analysis available without a slow recompute?

    Returns True if EITHER:
      (a) this session has already triggered a successful analyse_all, OR
      (b) the on-disk pipeline cache holds a fresh entry for every watchlist
          symbol at the requested (broker, toggles) combo.

    The disk-cache leg is critical on mobile: when iPad/Safari drops the
    websocket and you reopen the app, you get a brand-new session with
    empty session_state. Without the disk-cache check, you'd see "Compute
    playbook now" on every visit even though the data is sitting right
    there. With it, the page auto-loads from cache (~0.2 sec).

    The session_state leg short-circuits the disk-stat overhead within a
    single uptime period.
    """
    e = enh or all_off()
    # Note: Streamlit forbids session_state keys that start with underscore,
    # so the key uses a leading word.
    if st.session_state.get(f"pipeline_warm__{broker}__{e.short_label()}", False):
        return True
    # Fall back to on-disk inspection. Cheap (just stat() + mtime per file).
    try:
        toggle_kwargs = {
            "enh_garch": bool(getattr(e, "use_garch", False)),
            "enh_macro": bool(getattr(e, "use_macro_confirm", False)),
            "enh_regime_grade": bool(getattr(e, "use_regime_grade", False)),
            "enh_recency_weighted": bool(getattr(e, "use_recency_weighted", False)),
            "enh_drawdown_breaker": bool(getattr(e, "use_drawdown_breaker", False)),
        }
        symbols = [t.symbol for t in WATCHLIST]
        status = cache_status(symbols, broker, toggle_kwargs)
        return status["fresh"] == status["total"] and status["total"] > 0
    except Exception:  # noqa: BLE001
        # Disk inspection should never block UI rendering. Fall back to "cold".
        return False


def watchlist_cache_status(
    broker: str = "Stake", enh: Enhancements | None = None,
) -> dict[str, Any]:
    """Public helper for the home-page diagnostic.

    Returns the full cache_status() dict so the UI can show "21/21 fresh"
    or "3 missing, 18 fresh" and similar.
    """
    e = enh or all_off()
    toggle_kwargs = {
        "enh_garch": bool(getattr(e, "use_garch", False)),
        "enh_macro": bool(getattr(e, "use_macro_confirm", False)),
        "enh_regime_grade": bool(getattr(e, "use_regime_grade", False)),
        "enh_recency_weighted": bool(getattr(e, "use_recency_weighted", False)),
        "enh_drawdown_breaker": bool(getattr(e, "use_drawdown_breaker", False)),
    }
    symbols = [t.symbol for t in WATCHLIST]
    return cache_status(symbols, broker, toggle_kwargs)


def mark_watchlist_warm(broker: str = "Stake", enh: Enhancements | None = None) -> None:
    e = enh or all_off()
    try:
        st.session_state[f"pipeline_warm__{broker}__{e.short_label()}"] = True
    except Exception:
        # Warmth flag is a non-essential cache marker - never let it crash a page.
        pass


def analyse_all(
    broker: str = "Stake",
    progress: st.delta_generator.DeltaGenerator | None = None,
    enh: Enhancements | None = None,
    *,
    max_workers: int = DEFAULT_PARALLEL_WORKERS,
) -> list[dict[str, Any]]:
    """Run analyse_one for every watchlist symbol, returning results.

    Stocks are processed in parallel (default 4 worker threads) — each
    `analyse_one` call is independent and the heavy underlying libs
    (statsmodels, prophet, hmmlearn) release the GIL during model
    fitting, so threading gives a real ~3-4x speedup.

    Errors are captured per-symbol so one bad ticker doesn't kill the run.
    Results are returned in WATCHLIST order regardless of completion order,
    so downstream UI rendering stays deterministic across reloads.
    """
    e = enh or all_off()
    kw = _enh_kwargs(e)

    # Pre-allocate so we can fill positions out-of-order without affecting
    # the final list ordering (UI relies on stable order between reruns).
    rows: list[dict[str, Any] | None] = [None] * len(WATCHLIST)
    completed = [0]
    progress_lock = Lock()

    def _run(idx_ticker: tuple[int, Any]) -> tuple[int, dict[str, Any]]:
        i, t = idx_ticker
        try:
            res = analyse_one(t.symbol, broker=broker, **kw)
            return i, res
        except Exception as ex:  # noqa: BLE001
            return i, {
                "symbol": t.symbol, "name": t.name,
                "error": str(ex), "enhancements": e,
            }

    n = len(WATCHLIST)
    workers = max(1, min(max_workers, n))

    if workers == 1:
        # Sequential fallback — preserves the old behaviour for tests / debug.
        for i, t in enumerate(WATCHLIST):
            if progress is not None:
                progress.progress((i + 1) / n, text=f"Analysing {t.symbol}...")
            _, res = _run((i, t))
            rows[i] = res
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run, (i, t)): (i, t)
                for i, t in enumerate(WATCHLIST)
            }
            for fut in as_completed(futures):
                i, res = fut.result()
                rows[i] = res
                if progress is not None:
                    with progress_lock:
                        completed[0] += 1
                        sym = res.get("symbol", "?")
                        progress.progress(
                            completed[0] / n,
                            text=f"Analysed {sym} ({completed[0]}/{n})",
                        )

    mark_watchlist_warm(broker, e)
    # All slots are filled (each ticker either succeeded or returned an
    # error dict), so the cast back to a non-Optional list is safe.
    return [r for r in rows if r is not None]
