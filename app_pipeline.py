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

from datetime import datetime
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
from core.regime import detect_regime
from core.regime_grade import stratified_grade
from core.settings import Enhancements, all_off
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snapshot
from core.tickers import WATCHLIST
from core.volatility import VolatilityForecast, forecast_vol


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

    # Use 20 most-recent folds (~5 years) for the live trust grade -
    # this keeps the per-ticker run time manageable across the watchlist.
    # The Backtest Lab can override max_folds for deeper history.
    bt = backtest_all(df, horizon_days=90, market=t.market, broker=broker, max_folds=20)
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

    return {
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


def _enh_kwargs(enh: Enhancements) -> dict[str, Any]:
    return {
        "enh_label": enh.label or enh.short_label(),
        "enh_garch": enh.use_garch,
        "enh_macro": enh.use_macro_confirm,
        "enh_regime_grade": enh.use_regime_grade,
        "enh_recency_weighted": enh.use_recency_weighted,
        "enh_drawdown_breaker": enh.use_drawdown_breaker,
    }


def is_watchlist_warm(broker: str = "Stake", enh: Enhancements | None = None) -> bool:
    """Cheap check: has analyse_one been computed for every watchlist symbol?

    Per-broker per-toggle-combo flag. Survives page navigation within the
    same session, resets on restart.
    """
    e = enh or all_off()
    # Note: Streamlit forbids session_state keys that start with underscore,
    # so the key uses a leading word.
    return st.session_state.get(f"pipeline_warm__{broker}__{e.short_label()}", False)


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
) -> list[dict[str, Any]]:
    """Run analyse_one for every watchlist symbol, returning results.

    Errors are captured per-symbol so one bad ticker doesn't kill the run.
    """
    e = enh or all_off()
    kw = _enh_kwargs(e)
    rows: list[dict[str, Any]] = []
    n = len(WATCHLIST)
    for i, t in enumerate(WATCHLIST):
        if progress is not None:
            progress.progress((i + 1) / n, text=f"Analysing {t.symbol}...")
        try:
            rows.append(analyse_one(t.symbol, broker=broker, **kw))
        except Exception as ex:  # noqa: BLE001
            rows.append({"symbol": t.symbol, "name": t.name, "error": str(ex), "enhancements": e})
    mark_watchlist_warm(broker, e)
    return rows
