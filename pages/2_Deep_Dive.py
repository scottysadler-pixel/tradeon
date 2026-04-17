"""Deep Dive - single-stock analysis page.

Shows everything we know about one ticker: 20yr chart, stats, hold-window
heatmap, EOFY pattern, $1000 hypothetical, regime ribbon.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.analysis import (
    eofy_tax_loss_pattern,
    monthly_seasonality,
    quarterly_seasonality,
    stock_stats,
)
from core.backtest import backtest_all, trust_grade
from core.costs import net_trade_outcome
from core.data import fetch_history
from core.fx import normalise_to_aud
from core.hold_window import all_windows_matrix, best_windows
from core.regime import detect_regime, historical_regime_labels
from core.tickers import WATCHLIST
from ui_helpers import (
    aud,
    grade_badge,
    metric_with_help,
    page_setup,
    pct,
    regime_badge,
    render_disclaimer,
    ticker_picker,
)

page_setup("Deep Dive")

ticker = ticker_picker(default="MSFT")
broker = st.session_state.get("broker", "Stake")
capital = st.session_state.get("capital", 1000.0)


@st.cache_data(ttl=3600, show_spinner="Loading 20 years of history...")
def load_data(symbol: str) -> pd.DataFrame:
    t = next(x for x in WATCHLIST if x.symbol == symbol)
    raw = fetch_history(symbol, years=20, adjusted=True)
    return normalise_to_aud(raw, t)


@st.cache_data(ttl=3600, show_spinner="Backtesting...")
def run_backtest(symbol: str, market: str):
    df = load_data(symbol)
    return backtest_all(df, horizon_days=90, market=market, broker="Stake"), df


df = load_data(ticker.symbol)
results, _ = run_backtest(ticker.symbol, ticker.market)
stats = stock_stats(df)
grade = trust_grade(results)
regime = detect_regime(df)
spot = float(df["close"].iloc[-1])

# Header strip
hdr = st.columns([2, 1, 1, 1])
with hdr[0]:
    st.markdown(f"### {ticker.symbol} - {ticker.name}")
    st.caption(f"{ticker.sector} | {ticker.market} | spot {aud(spot)}")
with hdr[1]:
    st.markdown(f"Trust grade: {grade_badge(grade.grade)}", unsafe_allow_html=True)
    st.caption(f"Score {grade.score:.0f}/100")
with hdr[2]:
    st.markdown(f"Regime: {regime_badge(regime.label)}", unsafe_allow_html=True)
    st.caption(f"Confidence {regime.confidence:.0%}")
with hdr[3]:
    metric_with_help("Pattern strength", f"{stats.pattern_strength:.2f}", "Pattern Strength")

st.markdown("---")

# 20-year price chart with regime ribbon
st.markdown("#### 20-year price history (AUD)")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["date"], y=df["close"], mode="lines", name="Close (AUD)"))

regime_df = historical_regime_labels(df)
if not regime_df.empty:
    bear = regime_df[regime_df["regime"] == "bear"]
    if not bear.empty:
        # Add bear-period shading via vrects (grouped contiguous)
        bear = bear.copy()
        bear["date"] = pd.to_datetime(bear["date"])
        bear["block"] = (bear["date"].diff() > pd.Timedelta(days=2)).cumsum()
        for _, group in bear.groupby("block"):
            fig.add_vrect(
                x0=group["date"].iloc[0], x1=group["date"].iloc[-1],
                fillcolor="rgba(239,68,68,0.10)", line_width=0,
            )
fig.update_layout(
    height=420, margin=dict(l=10, r=10, t=20, b=10),
    xaxis_title=None, yaxis_title="Price (AUD)",
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Red shading = historically detected bear-regime periods.")

# Stats row
st.markdown("#### Stats")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    metric_with_help("CAGR", f"{stats.cagr_pct:+.1f}%", "CAGR")
with c2:
    metric_with_help("Annualised volatility", f"{stats.annualised_vol_pct:.1f}%", "Volatility")
with c3:
    metric_with_help("Max drawdown", f"{stats.max_drawdown_pct:.1f}%", "Max Drawdown")
with c4:
    metric_with_help("Sharpe", f"{stats.sharpe:.2f}", "Sharpe Ratio")
with c5:
    metric_with_help("History", f"{stats.sample_years:.1f} yrs", None)

st.markdown("---")

# Hold-window analysis
st.markdown("#### Best historical hold-windows")
windows = best_windows(df, top_n=5, min_hit_rate_pct=55.0)
if not windows:
    st.info("No statistically reliable hold-windows found for this stock.")
else:
    rows = []
    for w in windows:
        rows.append({
            "Buy month": w.buy_month, "Sell month": w.sell_month,
            "Avg return %": round(w.avg_return_pct, 2),
            "Median %": round(w.median_return_pct, 2),
            "Hit rate %": round(w.hit_rate_pct, 1),
            "Worst case %": round(w.worst_case_pct, 2),
            "Years observed": w.n_years,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# Heatmap of all windows
st.markdown("##### Hold-window heatmap (avg return %)")
matrix = all_windows_matrix(df)
if not matrix.empty:
    matrix_idx = matrix.set_index("buy_month")
    fig_hm = px.imshow(
        matrix_idx, aspect="auto", color_continuous_scale="RdYlGn",
        labels=dict(x="Hold length", y="Buy month", color="Avg return %"),
        zmin=-15, zmax=15,
    )
    fig_hm.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_hm, use_container_width=True)

st.markdown("---")

# Quarterly seasonality
st.markdown("#### Seasonality")
qcol, mcol = st.columns(2)
with qcol:
    st.markdown("**Quarterly**")
    qs = quarterly_seasonality(df)
    fig_q = px.bar(qs, x="quarter", y="mean_return_pct", color="hit_rate_pct",
                   color_continuous_scale="RdYlGn", range_color=[30, 80])
    fig_q.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                        yaxis_title="Avg return %")
    st.plotly_chart(fig_q, use_container_width=True)
with mcol:
    st.markdown("**Monthly**")
    ms = monthly_seasonality(df)
    fig_m = px.bar(ms, x="month", y="mean_return_pct", color="hit_rate_pct",
                   color_continuous_scale="RdYlGn", range_color=[30, 80])
    fig_m.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                        yaxis_title="Avg return %")
    st.plotly_chart(fig_m, use_container_width=True)

eofy = eofy_tax_loss_pattern(df)
if eofy:
    if eofy.get("pattern_detected"):
        st.success(f"**EOFY pattern detected**: {eofy['interpretation']}")
    else:
        st.info(f"EOFY check: {eofy['interpretation']}")

st.markdown("---")

# $1000 hypothetical
st.markdown("#### Net AUD outcome on a A$1000 trade")
held_days = st.slider("Hold period (days)", 30, 365, 90)
sim_buy = spot
sim_sell_pct = st.slider("Hypothetical sell-price move", -30.0, 50.0, 5.0, step=0.5)
sim_sell = sim_buy * (1 + sim_sell_pct / 100)
shares = int(capital // sim_buy)
out = net_trade_outcome(
    buy_price_aud=sim_buy, sell_price_aud=sim_sell, shares=shares,
    held_days=held_days, market=ticker.market, broker=broker,
)
n1, n2, n3, n4 = st.columns(4)
n1.metric("Gross gain", aud(out["gross_gain_aud"]))
n2.metric("Fees", aud(-out["fees_aud"]))
n3.metric("Tax", aud(-out["tax_aud"]))
n4.metric("Net AUD outcome", aud(out["net_gain_aud"]),
          delta=f"{out['net_return_pct']:+.1f}%")
if out["qualified_for_cgt_discount"]:
    st.success("Hold qualifies for the 50% CGT discount (>= 365 days).")
else:
    st.warning(
        "Short hold - full marginal tax applies. A 12-month hold would halve the tax."
    )

st.markdown("---")

# Backtest summary
st.markdown("#### Backtest summary (90-day horizon, walk-forward)")
br_rows = []
for k, r in results.items():
    br_rows.append({
        "Model": r.model_name, "Folds": r.n_folds,
        "MAPE %": round(r.mape_pct, 2),
        "Directional %": round(r.directional_accuracy_pct, 1),
        "CI coverage %": round(r.ci_coverage_pct, 1),
        "Paper-trade gross %": round(r.paper_trade_total_return_pct, 1),
        "Paper-trade net AUD %": round(r.paper_trade_net_return_pct_aud, 1),
    })
st.dataframe(pd.DataFrame(br_rows), hide_index=True, use_container_width=True)
st.caption(grade.interpretation)

render_disclaimer()
