"""Dashboard - watchlist overview with trust grades and signal status.

Heavy computation per stock is cached for an hour so flipping between
pages is snappy. First load takes a while because we backtest every
watchlist stock.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core.analysis import pattern_strength, stock_stats
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
from core.tickers import WATCHLIST, Ticker
from ui_helpers import (
    aud,
    grade_badge,
    page_setup,
    pct,
    regime_badge,
    render_disclaimer,
    signal_badge,
)

page_setup("Dashboard")


@st.cache_data(ttl=3600, show_spinner=False)
def analyse_one(symbol: str) -> dict:
    """Heavy work for one ticker. Cached for 1 hour."""
    t = next(x for x in WATCHLIST if x.symbol == symbol)
    df_native = fetch_history(symbol, years=20, adjusted=True)
    df = normalise_to_aud(df_native, t)
    if len(df) < 252 * 5:
        return {"symbol": symbol, "error": "Less than 5 years of data."}

    stats = stock_stats(df)
    bt = backtest_all(df, horizon_days=90, market=t.market, broker="Stake")
    grade = trust_grade(bt)
    regime = detect_regime(df)
    fcast = ensemble_forecast(df, horizon_days=90)
    naive = naive_forecast(df, horizon_days=90)
    tech = tech_snapshot(df)
    earnings = earnings_detect(df)
    spot = float(df["close"].iloc[-1])
    stops = stops_suggest(df, hold_days=90, current_price=spot)
    hold = upcoming_window(df, current_month=datetime.today().month)

    naive_drift = ((float(naive.forecast_mean[-1]) / spot) - 1) * 100
    sig = decide(
        trust=grade, regime=regime, hold=hold, forecast=fcast,
        technicals=tech, earnings=earnings, stops=stops,
        spot_price=spot, naive_baseline_drift_pct=naive_drift,
    )

    expected_pct = ((float(fcast.forecast_mean[-1]) / spot) - 1) * 100
    return {
        "symbol": symbol,
        "name": t.name,
        "sector": t.sector,
        "market": t.market,
        "spot_aud": spot,
        "trust_grade": grade.grade,
        "trust_score": grade.score,
        "regime": regime.label,
        "signal": sig.state,
        "signal_headline": sig.headline,
        "expected_90d_pct": expected_pct,
        "pattern_strength": stats.pattern_strength,
        "cagr_pct": stats.cagr_pct,
        "vol_pct": stats.annualised_vol_pct,
        "max_dd_pct": stats.max_drawdown_pct,
        "ensemble_directional_pct": bt["ensemble"].directional_accuracy_pct,
        "naive_directional_pct": bt["naive"].directional_accuracy_pct,
        "hold_window": hold.description if hold else "(no active window)",
    }


st.markdown(
    "Watchlist overview. **Default state is WAIT** - GO signals only appear when "
    "multiple indicators agree. Most days you'll see mostly grey. That's the system "
    "working correctly."
)

col_run, col_refresh = st.columns([3, 1])
with col_run:
    st.caption(
        f"Analysing **{len(WATCHLIST)} stocks** - first load takes a few minutes "
        "while we backtest every name. Subsequent loads are instant (cached 1hr)."
    )
with col_refresh:
    if st.button("Refresh all"):
        st.cache_data.clear()
        st.rerun()

progress = st.progress(0.0, text="Crunching...")
rows: list[dict] = []
errors: list[str] = []

for i, t in enumerate(WATCHLIST):
    progress.progress((i + 1) / len(WATCHLIST), text=f"Analysing {t.symbol}...")
    try:
        rows.append(analyse_one(t.symbol))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{t.symbol}: {e}")
progress.empty()

if errors:
    with st.expander(f"{len(errors)} symbol(s) failed to load"):
        for line in errors:
            st.warning(line)

ok_rows = [r for r in rows if "error" not in r]
df_summary = pd.DataFrame(ok_rows)

if df_summary.empty:
    st.error("No data loaded. Check internet connection and try Refresh.")
    st.stop()

# Headline counts
go_n = (df_summary["signal"] == "GO").sum()
wait_n = (df_summary["signal"] == "WAIT").sum()
avoid_n = (df_summary["signal"] == "AVOID").sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("GO signals", int(go_n))
m2.metric("WAIT", int(wait_n))
m3.metric("AVOID", int(avoid_n))
m4.metric("Stocks analysed", len(df_summary))

st.markdown("### Watchlist")

display = df_summary.sort_values(
    by=["signal", "trust_score"],
    key=lambda c: c.map({"GO": 0, "WAIT": 1, "AVOID": 2}) if c.name == "signal" else c,
    ascending=[True, False],
).reset_index(drop=True)

# Render the table manually with HTML badges for trust grade and signal
for _, r in display.iterrows():
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 3])
        with c1:
            st.markdown(f"**{r['symbol']}** - {r['name']}")
            st.caption(f"{r['sector']} | {r['market']}")
        with c2:
            st.markdown(f"Trust: {grade_badge(r['trust_grade'])}", unsafe_allow_html=True)
            st.caption(f"Score {r['trust_score']:.0f}/100")
        with c3:
            st.markdown(f"Regime: {regime_badge(r['regime'])}", unsafe_allow_html=True)
            st.caption(f"Pattern {r['pattern_strength']:.2f}")
        with c4:
            st.markdown(f"Signal: {signal_badge(r['signal'])}", unsafe_allow_html=True)
            st.caption(pct(r["expected_90d_pct"]) + " (90d)")
        with c5:
            st.write(r["signal_headline"])
            st.caption(f"Hold-window: {r['hold_window']}")

st.markdown("---")
st.markdown("### Stats summary")
st.dataframe(
    df_summary[
        [
            "symbol", "name", "spot_aud", "cagr_pct", "vol_pct", "max_dd_pct",
            "ensemble_directional_pct", "naive_directional_pct",
            "trust_grade", "regime", "signal",
        ]
    ].rename(columns={
        "spot_aud": "spot (A$)",
        "cagr_pct": "CAGR %",
        "vol_pct": "Vol %",
        "max_dd_pct": "Max DD %",
        "ensemble_directional_pct": "Ens. Dir. %",
        "naive_directional_pct": "Naive Dir. %",
    }),
    use_container_width=True,
    hide_index=True,
)

render_disclaimer()
