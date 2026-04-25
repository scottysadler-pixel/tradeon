"""Speculation register - manually tracked hypothetical predictions.

This page surfaces candidate ideas from TRADEON forecasts and lets the user
manually create/close paper predictions for a configurable holding horizon.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core.speculation import (
    CandidateBundle,
    SpeculationCandidate,
    SpeculationPrediction,
    add_prediction,
    build_speculation_candidates,
    close_prediction,
    compute_outcome,
    load_register,
    next_prediction_id,
    summarise,
)
from core.speculation_news import summarize_headlines
from core.tickers import WATCHLIST, by_symbol
from ui_helpers import aud, page_setup, pct, render_disclaimer


page_setup("Speculation")
broker = st.session_state.get("broker", "Stake")
capital_default = float(st.session_state.get("capital", 1000.0))


st.markdown(
    "Track speculative LONG and SHORT ideas you review manually. "
    "Candidates are suggestions only; the register is for your own tracking, "
    "with manual close on the date you actually choose."
)

with st.expander("How the Speculation tab works", expanded=False):
    st.markdown(
        """
        This tab is intentionally **manual-first**:

        1. Click **Refresh candidate list (quick)** to build a fresh shortlist from the
           current watchlist forecasts.
        2. Review candidates and choose one to seed a paper prediction.
        3. Use **Log a new paper prediction** to track that idea for the selected horizon.
        4. When your plan time window ends, use **Close an open prediction** and enter exit price.
        5. TRADEON calculates realised gain, fee impact, tax, and prediction error.

        Why there are no actions after this:

        - No auto-refresh: you decide when the candidate list is rebuilt.
        - No auto-trading: no real orders are placed from this page.
        - No auto-close: you decide when each hypothesis is closed.
        """
    )
    st.caption(
        "If you see an empty state on first open, it usually just means the candidates "
        "haven't been generated in this session yet."
    )

st.session_state.setdefault("spec_bundle", None)
st.session_state.setdefault("spec_last_refreshed", "")
st.session_state.setdefault("spec_stale_minutes", 60)


def _bundle_to_rows(bundle: CandidateBundle) -> pd.DataFrame:
    rows = []
    for c in bundle.long + bundle.short:
        rows.append({
            "Symbol": c.symbol,
            "Name": c.name,
            "Direction": c.expected_direction,
            f"Expected in {c.horizon_days}d %": f"{c.expected_return_pct_30d:+.2f}",
            "Trust": c.trust_grade,
            "Score": f"{c.score:.2f}",
            "Current": f"{c.spot_aud:.2f}",
            "Projected": f"{c.projected_exit_price_aud:.2f}",
            "Naive drift": f"{c.naivedrift_pct:+.2f}",
            "Notes": c.notes,
        })
    return pd.DataFrame(rows)


def _candidate_label(c: SpeculationCandidate) -> str:
    return (
        f"{c.symbol} {c.expected_direction} ({c.horizon_days}d) "
        f"{c.expected_return_pct_30d:+.1f}% (trust {c.trust_grade})"
    )


def _ticker_options() -> list[str]:
    return [t.symbol for t in WATCHLIST]


def _candidate_map(bundle: CandidateBundle | None) -> dict[str, SpeculationCandidate | None]:
    out = {"(manual)": None}
    if not bundle:
        return out
    for c in bundle.long + bundle.short:
        out[_candidate_label(c)] = c
    return out


st.markdown("### Candidate refresh")

c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
with c1:
    horizon_days = st.slider("Holding horizon (days)", min_value=7, max_value=90, value=30, step=1)
with c2:
    quick_size = st.slider("Quick scan size", min_value=5, max_value=12, value=8)
with c3:
    include_news = st.toggle("Use optional media headlines", value=False, help=(
        "If enabled, optional yfinance headlines are loaded only during manual refresh "
        "to keep the list fresh but still give you extra context."
    ))
with c4:
    stale_after_minutes = st.slider(
        "Treat list as stale after (minutes)",
        min_value=15,
        max_value=240,
        value=st.session_state["spec_stale_minutes"],
        step=15,
    )
    st.session_state["spec_stale_minutes"] = stale_after_minutes

col_run1, col_run2 = st.columns(2)
with col_run1:
    do_quick = st.button("Refresh candidate list (quick)", type="primary")
with col_run2:
    do_full = st.button("Run full watchlist scan (21 stocks)")

if do_quick or do_full:
    limit = quick_size if do_quick else None
    with st.spinner("Building speculative candidates..."):
        bundle = build_speculation_candidates(
            broker=broker,
            horizon_days=horizon_days,
            max_symbols=limit,
            include_news=include_news,
        )
    st.session_state["spec_bundle"] = bundle
    st.session_state["spec_last_refreshed"] = bundle.generated_at
    st.rerun()

bundle: CandidateBundle | None = st.session_state.get("spec_bundle")
if not bundle:
    st.info(
        "No candidates loaded yet. Click **Refresh candidate list (quick)** to build a "
        "manual shortlist, or **Run full watchlist scan** for all 21 symbols."
    )
    bundle = None
else:
    refreshed_at = st.session_state.get("spec_last_refreshed", "")
    if refreshed_at:
        try:
            last_seen = datetime.fromisoformat(refreshed_at)
            stale_at = (datetime.utcnow() - last_seen).total_seconds() / 60.0
            if stale_at <= stale_after_minutes:
                st.caption(f"Candidate list refreshed at {last_seen:%Y-%m-%d %H:%M:%SZ} UTC ({stale_at:.0f} min ago)")
            else:
                st.warning(
                    f"Candidate list is stale ({stale_at:.0f} minutes old). "
                    f"Click **Refresh candidate list (quick)** before acting."
                )
        except ValueError:
            st.caption(f"Candidate list timestamp: {refreshed_at}")

if bundle:
    st.caption(f"Generated: {bundle.generated_at} (scanned {bundle.scanned_count} symbols)")
    st.markdown("### Candidate ideas")
    tab_long, tab_short = st.tabs(["Long candidates", "Short candidates"])
    with tab_long:
        if bundle.long:
            st.dataframe(_bundle_to_rows(CandidateBundle(
                generated_at=bundle.generated_at,
                horizon_days=bundle.horizon_days,
                scanned_count=bundle.scanned_count,
                long=bundle.long,
                short=[],
            )), width="stretch", hide_index=True)
        else:
            st.caption("No LONG candidates passed the minimum score threshold.")
    with tab_short:
        if bundle.short:
            st.dataframe(_bundle_to_rows(CandidateBundle(
                generated_at=bundle.generated_at,
                horizon_days=bundle.horizon_days,
                scanned_count=bundle.scanned_count,
                long=[],
                short=bundle.short,
            )), width="stretch", hide_index=True)
        else:
            st.caption("No SHORT candidates passed the minimum score threshold.")

    with st.expander("Regenerating notes", expanded=False):
        if bundle.notes:
            for n in bundle.notes[:12]:
                st.caption(f"- {n}")
        else:
            st.caption("No notable skips.")

st.markdown("---")
st.markdown("### Register controls")

all_predictions = load_register()
open_predictions = [p for p in all_predictions if p.is_open]
closed_predictions = [p for p in all_predictions if not p.is_open]

seed_map = _candidate_map(bundle) if bundle else {"(manual)": None}
seed_names = list(seed_map.keys())

with st.form("new_prediction", clear_on_submit=True):
    st.markdown("#### Log a new paper prediction")
    seed_label = st.selectbox("Seed with candidate", seed_names, index=0)
    c1, c2, c3 = st.columns(3)
    with c1:
        seed = seed_map.get(seed_label)
        default_symbol = seed.symbol if seed else "MSFT"
        ticker_options = _ticker_options()
        symbol = st.selectbox("Symbol", ticker_options, index=ticker_options.index(default_symbol))
        direction = st.selectbox(
            "Direction",
            ["LONG", "SHORT"],
            index=0 if not seed or seed.expected_direction == "LONG" else 1,
        )
    with c2:
        default_entry = seed.entry_price_aud if seed else 0.0
        if default_entry <= 0:
            default_entry = 10.0
        entry_price = st.number_input("Entry price (AUD)", min_value=0.01, value=float(default_entry), step=0.01, format="%.4f")
        default_horizon = seed.horizon_days if seed else horizon_days
        hold_days = st.number_input(
            "Hold horizon (days)",
            min_value=1,
            value=int(default_horizon),
            step=1,
            help="Default from the candidate list is 30 days unless you override.",
        )
    with c3:
        default_pred = seed.expected_return_pct_30d if seed else 0.0
        predicted = st.number_input("Predicted return %", value=float(default_pred), step=0.1, format="%.2f")
        notes = st.text_input("Notes (optional)")
    exit_date = st.date_input("Target exit date", value=date.today() + timedelta(days=int(hold_days)))
    capital = st.number_input("Capital (AUD)", min_value=100.0, value=capital_default, step=100.0)
    submitted = st.form_submit_button("Add prediction", type="secondary")
    if submitted:
        t = by_symbol(symbol)
        try:
            prediction = SpeculationPrediction(
                prediction_id=next_prediction_id(),
                created_at=date.today().isoformat(),
                symbol=symbol,
                name=t.name if t else symbol,
                market=t.market if t else "ASX",
                direction=direction,
                broker=broker,
                capital_aud=float(capital),
                horizon_days=int(hold_days),
                entry_price_aud=float(entry_price),
                expected_return_pct=float(predicted),
                predicted_exit_date=exit_date.isoformat(),
                notes=notes,
            )
            add_prediction(prediction)
            st.success(f"Added prediction {prediction.prediction_id} for {symbol} ({direction}).")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Failed to add prediction: {e}")

if bundle and include_news:
    with st.expander("Headline context from latest candidates"):
        for candidate in bundle.long[:3] + bundle.short[:3]:
            ctx = summarize_headlines(candidate.symbol, max_items=3)
            st.markdown(f"**{candidate.symbol}**")
            if ctx["available"]:
                st.caption(f"Sentiment: {ctx['label']} ({ctx['avg_sentiment']:+.2f})")
                for item in ctx["items"][:2]:
                    st.caption(f"- {item['title']}")
            else:
                st.caption("No headlines available right now.")

st.markdown("---")
st.markdown("### Close an open prediction")

if not open_predictions:
    st.info("No open predictions.")
else:
    with st.form("close_form", clear_on_submit=True):
        options = {
            (
                f"{p.prediction_id} | {p.symbol} {p.direction} | "
                f"{p.invested_aud:.2f} @ {p.entry_price_aud:.2f}"
            ): p.prediction_id
            for p in open_predictions
        }
        pick = st.selectbox("Open prediction", list(options.keys()))
        target_id = options[pick]
        c1, c2 = st.columns([1, 1])
        with c1:
            close_dt = st.date_input("Close date", value=date.today())
        with c2:
            close_px = st.number_input(
                "Close price (AUD)",
                min_value=0.0001,
                value=10.0,
                step=0.01,
            )
        close_note = st.text_input("Closing note (optional)")
        do_close = st.form_submit_button("Close selected prediction", type="primary")
        if do_close:
            try:
                closed, outcome = close_prediction(
                    target_id, close_dt, float(close_px), notes=close_note
                )
                st.success(
                    f"Closed {closed.prediction_id}: {outcome.direction} expected "
                    f"{outcome.predicted_return_pct:+.2f}% vs actual {outcome.actual_return_pct:+.2f}%; "
                    f"net after tax {pct(outcome.net_pct)} on {outcome.shares} shares."
                )
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Failed to close prediction: {e}")

st.markdown("---")
st.markdown("### Register summary")
summary = summarise(all_predictions)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total predictions", summary.total_predictions, delta=f"{summary.open_count} open")
col2.metric("Closed (realised)", summary.closed_count, delta=f"{summary.hit_rate_pct:.0f}% hit rate")
col3.metric("Realised net (after tax)", aud(summary.realized_net_aud), delta=f"{summary.realized_pct:.1f}%")
col4.metric("Avg actual return", f"{summary.avg_actual_return_pct:+.2f}%" if summary.avg_actual_return_pct is not None else "-", delta=f"{summary.avg_days_held:.0f} days held")

if summary.closed_count:
    st.caption(
        f"Prediction error (actual - predicted): "
        f"{summary.avg_pred_error_pct:+.2f}%"
        if summary.avg_pred_error_pct is not None
        else ""
    )


st.markdown("### Open predictions")
if open_predictions:
    open_rows = []
    for p in open_predictions:
        open_rows.append({
            "ID": p.prediction_id,
            "Symbol": p.symbol,
            "Direction": p.direction,
            "Status": p.status.upper(),
            "Entry": f"{p.entry_price_aud:.2f}",
            "Capital": f"{p.capital_aud:.2f}",
            "Expected %": f"{p.expected_return_pct:+.2f}",
            "Predicted exit": p.predicted_exit_date,
            "Created": p.created_at,
            "Notes": p.notes,
        })
    st.dataframe(pd.DataFrame(open_rows), hide_index=True, width="stretch")
else:
    st.caption("No open items yet.")

if closed_predictions:
    st.markdown("### Closed predictions")
    closed_rows = []
    for p in closed_predictions:
        if not p.close_price_aud or not p.close_date:
            continue
        outcome = compute_outcome(
            p,
            close_date=datetime.fromisoformat(p.close_date).date(),
            close_price_aud=float(p.close_price_aud),
        )
        closed_rows.append({
            "ID": p.prediction_id,
            "Symbol": p.symbol,
            "Direction": p.direction,
            "Close": p.close_date,
            "Actual %": f"{outcome.actual_return_pct:+.2f}",
            "Predicted %": f"{outcome.predicted_return_pct:+.2f}",
            "Error %": f"{outcome.prediction_error_pct:+.2f}",
            "Net after-tax": aud(outcome.net_after_tax_aud),
            "Net %": f"{outcome.net_pct:+.2f}",
            "Shares": outcome.shares,
        })
    if closed_rows:
        st.dataframe(pd.DataFrame(closed_rows), hide_index=True, width="stretch")

st.markdown("---")
render_disclaimer()

