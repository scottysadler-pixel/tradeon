"""Forward Outlook - active GO signals only.

The page that actually drives action. Quiet most of the time. Each green
card includes a step-by-step trade walkthrough.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app_pipeline import DEFAULT_PARALLEL_WORKERS, analyse_one, mark_watchlist_warm
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

from app_pipeline import _enh_kwargs  # defensive single source of truth
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

progress = st.progress(0.0, text="Scanning watchlist...")
candidates: list[dict] = []
_warnings: list[str] = []
_n = len(WATCHLIST)
_completed = [0]
_progress_lock = Lock()
_kw = _enh_kwargs(enh)


def _eval_one(t):
    try:
        return t.symbol, analyse_one(t.symbol, broker=broker, **_kw), None
    except Exception as e:  # noqa: BLE001
        return t.symbol, None, str(e)


with ThreadPoolExecutor(max_workers=min(DEFAULT_PARALLEL_WORKERS, _n)) as _pool:
    _futs = [_pool.submit(_eval_one, t) for t in WATCHLIST]
    for _fut in as_completed(_futs):
        sym, res, err = _fut.result()
        if err is not None:
            _warnings.append(f"{sym}: {err}")
        elif res is not None and "error" not in res:
            candidates.append(res)
        with _progress_lock:
            _completed[0] += 1
            progress.progress(
                _completed[0] / _n,
                text=f"Evaluated {sym} ({_completed[0]}/{_n})",
            )

for _w in _warnings:
    st.warning(_w)
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
        if getattr(enh, "use_garch", False) and c.get("vol") is not None:
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
        m1.metric(
            "Expected return",
            pct(sig.expected_return_pct),
            help=(
                "Forecast lift over the suggested hold window, **net of broker "
                "fees and AU CGT**, in AUD. A positive number is what you'd "
                "actually pocket. Treat anything under +5% as marginal — the "
                "trust grade better be A or B before you act on a thin lift."
            ),
        )
        m2.metric(
            "Position size",
            aud(size.suggested_aud),
            delta=f"{size.shares} shares{size_note}",
            help=(
                "Suggested AUD amount and share count, sized so this trade "
                "carries similar dollar-risk to your other watchlist trades. "
                "Scaled by trailing 90-day volatility (and by GARCH if "
                "toggle 1 is on). Smaller for jumpy stocks, larger for calm ones."
            ),
        )
        m3.metric(
            "Stop-loss",
            aud(sig.suggested_stop_price),
            help=(
                "The price you decide IN ADVANCE to sell at if the trade goes "
                "against you. Set roughly 1 typical drawdown below entry. "
                "Most brokers let you attach this as a conditional sell when "
                "you place the buy. **No exceptions** if it triggers."
            ),
        )
        m4.metric(
            "Confidence",
            f"{sig.confidence:.0%}",
            help=(
                "How strongly the decider's signals agreed. 100% = every "
                "check passed cleanly; 50% = it was a near miss. If a safety "
                "filter (macro or drawdown breaker) downgraded a GO, you "
                "won't see this card at all — only clean, high-confidence "
                "GOs reach this page."
            ),
        )

        if getattr(enh, "use_garch", False) and c.get("vol") is not None:
            st.caption(f"Volatility forecast ({c['vol'].method}): {c['vol'].interpretation}")
        if getattr(enh, "use_macro_confirm", False) and c.get("macro") is not None:
            st.caption(f"Macro: {c['macro'].interpretation}")
        if getattr(enh, "use_recency_weighted", False) and c.get("recency_weights") is not None:
            st.caption(f"Forecast weighting: {c['recency_weights'].interpretation}")
        if getattr(enh, "use_drawdown_breaker", False) and c.get("breaker") is not None:
            st.caption(f"Circuit-breaker: {c['breaker'].interpretation}")

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
