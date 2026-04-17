"""Forward Outlook - active GO signals only.

The page that actually drives action. Quiet most of the time. Each green
card includes a step-by-step trade walkthrough.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.earnings_proxy import detect as earnings_detect
from core.forecast import ensemble_forecast, naive_forecast
from core.fx import normalise_to_aud
from core.hold_window import upcoming_window
from core.position_size import suggest as size_suggest
from core.regime import detect_regime
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snapshot
from core.tickers import WATCHLIST
from core.trade_walkthrough import generate as walkthrough_gen
from ui_helpers import (
    aud,
    grade_badge,
    page_setup,
    pct,
    regime_badge,
    render_disclaimer,
    signal_badge,
)

page_setup("Forward Outlook")

broker = st.session_state.get("broker", "Stake")
capital = st.session_state.get("capital", 1000.0)

st.markdown(
    "Stocks with currently active GO signals are listed below with a complete "
    "trade plan. **It is normal for this list to be empty or very short** - "
    "the system only acts when multiple indicators agree."
)


@st.cache_data(ttl=3600, show_spinner=False)
def evaluate_one(symbol: str):
    t = next(x for x in WATCHLIST if x.symbol == symbol)
    raw = fetch_history(symbol, years=20, adjusted=True)
    df = normalise_to_aud(raw, t)
    if len(df) < 252 * 5:
        return None

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
    return {"ticker": t, "df": df, "grade": grade, "regime": rg, "forecast": fcast,
            "signal": sig, "spot": spot, "stops": stops, "hold": hold,
            "earnings": earn, "naive": naive}


progress = st.progress(0.0, text="Scanning watchlist...")
candidates: list[dict] = []
for i, t in enumerate(WATCHLIST):
    progress.progress((i + 1) / len(WATCHLIST), text=f"Evaluating {t.symbol}...")
    try:
        res = evaluate_one(t.symbol)
        if res:
            candidates.append(res)
    except Exception as e:  # noqa: BLE001
        st.warning(f"{t.symbol}: {e}")
progress.empty()

go_signals = [c for c in candidates if c["signal"].state == "GO"]
go_signals.sort(key=lambda c: c["signal"].confidence, reverse=True)

if not go_signals:
    st.info(
        "**No GO signals right now.** This is the system working correctly - it "
        "is silent when multiple indicators do not agree. Check back in a few "
        "days. In the meantime, the Dashboard shows current state of every "
        "watchlist stock."
    )
else:
    st.success(f"**{len(go_signals)} GO signal(s) currently active**")

for c in go_signals:
    t = c["ticker"]
    sig = c["signal"]
    fcast = c["forecast"]

    with st.container(border=True):
        head = st.columns([3, 1, 1, 1])
        with head[0]:
            st.markdown(f"### {t.symbol} - {t.name}")
            st.caption(f"{t.sector} | {t.market} | spot {aud(c['spot'])}")
        with head[1]:
            st.markdown(f"Trust {grade_badge(c['grade'].grade)}", unsafe_allow_html=True)
        with head[2]:
            st.markdown(f"Regime {regime_badge(c['regime'].label)}", unsafe_allow_html=True)
        with head[3]:
            st.markdown(f"Signal {signal_badge(sig.state)}", unsafe_allow_html=True)

        st.markdown(f"**{sig.headline}**")

        # Forecast chart
        df = c["df"].tail(252 * 2)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=df["close"], mode="lines", name="History"))
        fig.add_trace(go.Scatter(x=fcast.forecast_dates, y=fcast.forecast_mean,
                                 mode="lines", name="Forecast", line=dict(color="#22c55e")))
        fig.add_trace(go.Scatter(
            x=list(fcast.forecast_dates) + list(fcast.forecast_dates[::-1]),
            y=list(fcast.forecast_upper) + list(fcast.forecast_lower[::-1]),
            fill="toself", fillcolor="rgba(34,197,94,0.18)",
            line=dict(width=0), name="80% confidence",
        ))
        fig.update_layout(height=320, hovermode="x unified", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Position sizing
        size = size_suggest(capital_aud=capital, spot_price_aud=c["spot"], df=c["df"])

        # Trade walkthrough
        wt = walkthrough_gen(sig, t, capital_aud=capital, broker=broker, spot_price_aud=c["spot"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Expected return", pct(sig.expected_return_pct))
        m2.metric("Position size", aud(size.suggested_aud), delta=f"{size.shares} shares")
        m3.metric("Stop-loss", aud(sig.suggested_stop_price))
        m4.metric("Confidence", f"{sig.confidence:.0%}")

        with st.expander("How to actually place this trade"):
            for step in wt.steps:
                st.markdown(step)
            st.info(wt.summary)

        with st.expander("Why this signal fired (reasons)"):
            for r in sig.reasons:
                st.markdown(f"- {r}")

st.markdown("---")
render_disclaimer()
