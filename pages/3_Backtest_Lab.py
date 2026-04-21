"""Backtest Lab - interactive playground.

Pick any ticker, model and horizon; see the full walk-forward report.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.backtest import backtest_model
from core.backtest_cache import (
    cache_count as bt_cache_count,
    load_cached as bt_load_cached,
    save_cached as bt_save_cached,
)
from core.data import fetch_history
from core.forecast import (
    arima_forecast,
    ensemble_forecast,
    holt_winters_forecast,
    naive_forecast,
    seasonal_naive_forecast,
)
from core.fx import normalise_to_aud
from ui_helpers import page_setup, render_disclaimer, ticker_picker

page_setup("Backtest Lab")

st.markdown(
    "Pick a stock, a model and a horizon. The lab walk-forward backtests it across "
    "history and shows you the prediction-vs-actual comparison."
)

ticker = ticker_picker(default="MSFT", key="bt_ticker")
broker = st.session_state.get("broker", "Stake")

c1, c2, c3 = st.columns(3)
with c1:
    model_key = st.selectbox(
        "Model",
        ["ensemble", "naive", "seasonal", "holt_winters", "arima"],
        index=0,
    )
with c2:
    horizon = st.slider("Forecast horizon (days)", 30, 180, 90)
with c3:
    coverage = st.selectbox(
        "History to test",
        ["Last 5 years (~20 folds)", "Last 10 years (~40 folds)", "All available (up to 60 folds)"],
        index=2,
        help=(
            "How much of the past to replay. The lab walks forward in 90-day "
            "steps; more folds = more honest stress-test, but takes longer."
        ),
    )

_FOLD_CAP = {
    "Last 5 years (~20 folds)": 20,
    "Last 10 years (~40 folds)": 40,
    "All available (up to 60 folds)": 60,
}[coverage]

MODEL_MAP = {
    "naive": naive_forecast,
    "seasonal": seasonal_naive_forecast,
    "holt_winters": holt_winters_forecast,
    "arima": arima_forecast,
    "ensemble": ensemble_forecast,
}


@st.cache_data(ttl=3600, show_spinner="Loading data...")
def get_df(symbol: str) -> pd.DataFrame:
    from core.tickers import by_symbol
    raw = fetch_history(symbol, years=20, adjusted=True)
    return normalise_to_aud(raw, by_symbol(symbol))


# Two-tier cache for the expensive backtest_model() call:
#   1. @st.cache_data    — in-process memory, instant within a session
#   2. backtest_cache.py — on-disk pickle, instant across sessions and
#                          across Streamlit Cloud restarts (within one
#                          container's uptime period)
# Together: first time you click a (symbol, model, horizon, folds)
# combo costs ~30 sec; every subsequent visit is ~50 ms forever (or
# until the 7-day TTL expires).
@st.cache_data(ttl=3600, show_spinner=False)
def cached_backtest(symbol: str, model_key: str, horizon: int,
                    market: str, broker: str, max_folds: int):
    cached = bt_load_cached(symbol, model_key, horizon, market, broker, max_folds)
    if cached is not None:
        return cached
    df = get_df(symbol)
    result = backtest_model(
        df, MODEL_MAP[model_key],
        horizon_days=horizon, market=market, broker=broker,
        max_folds=max_folds, prefer_recent=True,
    )
    try:
        bt_save_cached(symbol, model_key, horizon, market, broker, max_folds, result)
    except Exception:  # noqa: BLE001
        pass
    return result


df = get_df(ticker.symbol)

with st.spinner(f"Backtesting {model_key} on {ticker.symbol} ({_FOLD_CAP} folds)..."):
    result = cached_backtest(
        ticker.symbol, model_key, horizon,
        ticker.market, broker, _FOLD_CAP,
    )

st.markdown(f"#### Results: {result.model_name}")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Folds", result.n_folds, help="Number of historical periods backtested.")
m2.metric("MAPE", f"{result.mape_pct:.2f}%")
m3.metric("Directional", f"{result.directional_accuracy_pct:.1f}%")
m4.metric("CI coverage", f"{result.ci_coverage_pct:.1f}%")
m5.metric("Paper-trade net AUD", f"{result.paper_trade_net_return_pct_aud:+.1f}%")

if not result.sample_predictions.empty:
    sp_dates = pd.to_datetime(result.sample_predictions["fold_end"])
    st.caption(
        f"Coverage: {sp_dates.min():%Y-%m-%d} to {sp_dates.max():%Y-%m-%d} "
        f"({len(sp_dates)} fold ends). Each point = a real historical date "
        "where the model was trained ONLY on data before it, then asked "
        f"\"where will price be in {horizon} days?\""
    )

st.markdown("##### Predictions vs actuals")
sp = result.sample_predictions
if not sp.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sp["fold_end"], y=sp["actual_end"], mode="lines+markers", name="Actual"))
    fig.add_trace(go.Scatter(x=sp["fold_end"], y=sp["predicted_end"], mode="lines+markers", name="Predicted"))
    fig.update_layout(height=400, xaxis_title=None, yaxis_title="Price (AUD)",
                      hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")

    sp_display = sp.copy()
    sp_display["fold_end"] = pd.to_datetime(sp_display["fold_end"]).dt.strftime("%Y-%m-%d")
    st.dataframe(sp_display, hide_index=True, width="stretch")
else:
    st.warning("No fold data - try a longer history or a shorter horizon.")

st.caption(
    "Walk-forward = at each historical date, train ONLY on data up to that date, "
    "then check the prediction against what really happened next. The most honest "
    "way to test a forecasting strategy."
)

with st.expander("Cache health", expanded=False):
    n_cached = bt_cache_count()
    st.caption(
        f"**{n_cached}** backtest combo(s) cached on disk. Each combo "
        "(symbol × model × horizon × fold-cap) takes ~30 sec the first "
        "time and ~50 ms every subsequent visit (within 7 days). The "
        "cache builds up naturally as you explore — combos you never "
        "open are never computed."
    )

render_disclaimer()
