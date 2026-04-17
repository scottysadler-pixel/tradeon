"""Shared per-stock analysis pipeline.

Both the Dashboard, Forward Outlook and Today's Playbook need the same
expensive computation per ticker. Extracting it here lets Streamlit's
@st.cache_data share results across pages: the first page that triggers
the work pays the cost, all subsequent pages get instant cache hits.

This module is allowed to import streamlit (for caching) but the heavy
lifting still lives in the streamlit-free `core/` package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.earnings_proxy import detect as earnings_detect
from core.forecast import ensemble_forecast, naive_forecast
from core.fx import normalise_to_aud
from core.hold_window import upcoming_window
from core.regime import detect_regime
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snapshot
from core.tickers import WATCHLIST


@st.cache_data(ttl=3600, show_spinner=False)
def analyse_one(symbol: str, broker: str = "Stake") -> dict[str, Any]:
    """Run the full per-stock pipeline. Cached for 1 hour, shared across pages.

    Returns a dict with both summary fields (for Dashboard tables) and
    rich objects (for Forward Outlook charts).
    """
    t = next(x for x in WATCHLIST if x.symbol == symbol)
    df_native = fetch_history(symbol, years=20, adjusted=True)
    df = normalise_to_aud(df_native, t)

    if len(df) < 252 * 5:
        return {
            "symbol": symbol,
            "name": t.name,
            "ticker": t,
            "error": "Less than 5 years of data.",
        }

    bt = backtest_all(df, horizon_days=90, market=t.market, broker=broker)
    grade = trust_grade(bt)
    rg = detect_regime(df)
    fcast = ensemble_forecast(df, horizon_days=90)
    naive = naive_forecast(df, horizon_days=90)
    snap = tech_snapshot(df)
    earn = earnings_detect(df)
    spot = float(df["close"].iloc[-1])
    stops = stops_suggest(df, hold_days=90, current_price=spot)
    hold = upcoming_window(df, current_month=datetime.today().month)

    naive_drift = ((float(naive.forecast_mean[-1]) / spot) - 1) * 100
    sig = decide(
        trust=grade, regime=rg, hold=hold, forecast=fcast,
        technicals=snap, earnings=earn, stops=stops,
        spot_price=spot, naive_baseline_drift_pct=naive_drift,
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
    }


def is_watchlist_warm(broker: str = "Stake") -> bool:
    """Cheap check: has analyse_one been computed for every watchlist symbol?

    Uses Streamlit's session_state - we set a flag once a full pass completes.
    Survives page navigation within the same session, but resets on restart.
    """
    return st.session_state.get(f"_pipeline_warm__{broker}", False)


def mark_watchlist_warm(broker: str = "Stake") -> None:
    st.session_state[f"_pipeline_warm__{broker}"] = True


def analyse_all(
    broker: str = "Stake",
    progress: st.delta_generator.DeltaGenerator | None = None,
) -> list[dict[str, Any]]:
    """Run analyse_one for every watchlist symbol, returning results.

    Errors are captured per-symbol so one bad ticker doesn't kill the run.
    Pass a progress widget to render incremental updates.
    """
    rows: list[dict[str, Any]] = []
    n = len(WATCHLIST)
    for i, t in enumerate(WATCHLIST):
        if progress is not None:
            progress.progress((i + 1) / n, text=f"Analysing {t.symbol}...")
        try:
            rows.append(analyse_one(t.symbol, broker=broker))
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": t.symbol, "name": t.name, "error": str(e)})
    mark_watchlist_warm(broker)
    return rows
