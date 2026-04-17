"""Forward Outlook - active GO signals only.

The page that actually drives action. Quiet most of the time. Each green
card includes a step-by-step trade walkthrough.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app_pipeline import analyse_one, mark_watchlist_warm
from core.broker_links import (
    broker_link,
    confirmation_checklist,
    order_ticket,
    yahoo_chart_url,
)
from core.position_size import suggest as size_suggest
from core.settings import from_session as enh_from_session
from core.tickers import WATCHLIST
from core.volatility import garch_position_multiplier
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
enh = enh_from_session(st.session_state)

st.markdown(
    "Stocks with currently active GO signals are listed below with a complete "
    "trade plan. **It is normal for this list to be empty or very short** - "
    "the system only acts when multiple indicators agree."
)

if enh.any_active():
    st.info(f"Active enhancements: **{enh.short_label()}** - signals reflect these toggles.")

progress = st.progress(0.0, text="Scanning watchlist...")
candidates: list[dict] = []
for i, t in enumerate(WATCHLIST):
    progress.progress((i + 1) / len(WATCHLIST), text=f"Evaluating {t.symbol}...")
    try:
        res = analyse_one(
            t.symbol, broker=broker,
            enh_label=enh.short_label(), enh_garch=enh.use_garch,
            enh_macro=enh.use_macro_confirm, enh_regime_grade=enh.use_regime_grade,
        )
        if "error" not in res:
            candidates.append(res)
    except Exception as e:  # noqa: BLE001
        st.warning(f"{t.symbol}: {e}")
progress.empty()
mark_watchlist_warm(broker, enh)

go_signals = [c for c in candidates if c["signal"] == "GO"]
go_signals.sort(key=lambda c: c["signal_obj"].confidence, reverse=True)

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
    sig = c["signal_obj"]
    fcast = c["forecast"]
    spot = c["spot_aud"]

    with st.container(border=True):
        head = st.columns([3, 1, 1, 1])
        with head[0]:
            st.markdown(f"### {t.symbol} - {t.name}")
            st.caption(f"{t.sector} | {t.market} | spot {aud(spot)}")
        with head[1]:
            st.markdown(f"Trust {grade_badge(c['trust_grade'])}", unsafe_allow_html=True)
        with head[2]:
            st.markdown(f"Regime {regime_badge(c['regime'])}", unsafe_allow_html=True)
        with head[3]:
            st.markdown(f"Signal {signal_badge(c['signal'])}", unsafe_allow_html=True)

        st.markdown(f"**{sig.headline}**")

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

        size = size_suggest(capital_aud=capital, spot_price_aud=spot, df=c["df"])

        # GARCH-aware sizing: shrink when storm expected, grow when calm expected
        size_note = ""
        if enh.use_garch and c.get("vol") is not None:
            mult = garch_position_multiplier(c["vol"])
            adj_aud = size.suggested_aud * mult
            adj_shares = int(adj_aud // spot) if spot > 0 else 0
            from core.position_size import PositionSize
            size = PositionSize(
                suggested_aud=adj_shares * spot,
                shares=adj_shares,
                pct_of_capital=(adj_shares * spot / capital) * 100 if capital else 0,
                explanation=size.explanation + f" GARCH multiplier x{mult:.2f} applied.",
            )
            size_note = f" (GARCH x{mult:.2f})"

        wt = walkthrough_gen(sig, t, capital_aud=capital, broker=broker, spot_price_aud=spot)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Expected return", pct(sig.expected_return_pct))
        m2.metric("Position size", aud(size.suggested_aud), delta=f"{size.shares} shares{size_note}")
        m3.metric("Stop-loss", aud(sig.suggested_stop_price))
        m4.metric("Confidence", f"{sig.confidence:.0%}")

        if enh.use_garch and c.get("vol") is not None:
            st.caption(f"Volatility forecast ({c['vol'].method}): {c['vol'].interpretation}")
        if enh.use_macro_confirm and c.get("macro") is not None:
            st.caption(f"Macro: {c['macro'].interpretation}")

        with st.expander("How to actually place this trade", expanded=True):
            ticket = order_ticket(sig, t, shares=size.shares, spot_price_aud=spot)
            st.markdown("**Copy this order ticket** (click the icon at the top-right of the box):")
            st.code(ticket, language="text")
            st.caption(
                "Paste this into your broker's order screen, your trade journal, "
                "or a notes app for a paper trail."
            )

            link = broker_link(broker, t)
            link_cols = st.columns(2)
            with link_cols[0]:
                st.link_button(link.label, link.url, use_container_width=True)
                st.caption(link.note)
            with link_cols[1]:
                st.link_button(
                    "View chart on Yahoo Finance",
                    yahoo_chart_url(t),
                    use_container_width=True,
                )
                st.caption("Independent sanity-check of price + recent news.")

            st.markdown("**Pre-submit checks:**")
            for check in confirmation_checklist(sig, t):
                st.markdown(f"- {check}")

            st.markdown("---")
            st.markdown("**Detailed step-by-step:**")
            for step in wt.steps:
                st.markdown(step)
            st.info(wt.summary)

        with st.expander("Why this signal fired (reasons)"):
            for r in sig.reasons:
                st.markdown(f"- {r}")

st.markdown("---")
render_disclaimer()
