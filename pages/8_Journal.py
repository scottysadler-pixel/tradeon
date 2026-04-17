"""Trade Journal - log real trades and grade yourself.

The journal tracks YOUR trades (not TRADEON's predictions) and reports:
- Your real net AUD return after fees + AU CGT
- Your hit rate
- How your real outcomes compare to what TRADEON predicted at entry
- How trades you took AGAINST a WAIT signal panned out

Persistence note: data lives in data_cache/journal.csv. On Streamlit
Cloud's free tier the cache is ephemeral - use the Download button at
the bottom to keep a permanent copy you control, and Upload to restore.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.journal import (
    JOURNAL_PATH,
    JournalEntry,
    add_entry,
    close_trade,
    compute_outcome,
    delete_entry,
    export_csv,
    import_csv,
    load_journal,
    next_trade_id,
    summarise,
)
from core.tickers import WATCHLIST, by_symbol
from ui_helpers import aud, page_setup, pct, render_disclaimer

page_setup("Trade Journal")
broker = st.session_state.get("broker", "Stake")

st.markdown(
    "Log trades you actually placed. The journal computes real net AUD "
    "returns after fees + AU CGT, your personal hit rate, and how often "
    "TRADEON's predictions matched what really happened."
)

if not JOURNAL_PATH.exists():
    st.info(
        "No journal file yet. Add your first trade below, or upload an "
        "existing journal CSV from a previous session."
    )

# ----- Summary panel -----
entries = load_journal()
if entries:
    summ = summarise(entries)
    st.markdown("### Your performance")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trades logged", summ.total_trades, delta=f"{summ.open_trades} open")
    m2.metric(
        "Realised net (after tax)",
        aud(summ.realised_net_aud),
        delta=f"{summ.realised_pct:+.1f}% avg",
    )
    m3.metric(
        "Hit rate",
        f"{summ.hit_rate_pct:.0f}%",
        delta=f"{summ.closed_trades} closed",
    )
    m4.metric(
        "Avg days held",
        f"{summ.average_days_held:.0f}",
        help="Below 365 = full marginal CGT applies. 365+ = 50% CGT discount.",
    )

    if summ.closed_with_predictions:
        st.markdown("### vs TRADEON")
        v1, v2, v3 = st.columns(3)
        v1.metric(
            "Trades with a TRADEON prediction at entry",
            summ.closed_with_predictions,
        )
        if summ.avg_prediction_error_pct is not None:
            v2.metric(
                "Avg prediction error",
                f"{summ.avg_prediction_error_pct:+.1f}pp",
                help=(
                    "Actual return minus predicted return, in percentage "
                    "points. Positive = TRADEON underestimated; "
                    "negative = TRADEON overestimated."
                ),
            )
        if summ.direction_called_correctly_pct is not None:
            v3.metric(
                "Direction called correctly",
                f"{summ.direction_called_correctly_pct:.0f}%",
            )

    if summ.trades_taken_against_wait:
        st.markdown("### When you traded against a WAIT signal")
        rate = summ.against_wait_hit_rate_pct or 0
        verdict = (
            "you usually beat the system" if rate > 60
            else "you broke even" if 40 <= rate <= 60
            else "the system would have saved you money"
        )
        st.caption(
            f"You took **{summ.trades_taken_against_wait}** trades when "
            f"TRADEON said WAIT or AVOID. Of those, **{rate:.0f}%** were "
            f"profitable - so on average **{verdict}**."
        )

    st.markdown("---")

# ----- Add new trade form -----
st.markdown("### Log a new trade")

mode = st.radio(
    "Trade mode",
    ["Open new trade (buy)", "Close existing trade (sell)"],
    horizontal=True,
)

if mode == "Open new trade (buy)":
    with st.form("new_trade", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            wl_symbols = [t.symbol for t in WATCHLIST]
            wl_labels = {t.symbol: t.display for t in WATCHLIST}
            symbol_choice = st.selectbox(
                "Ticker",
                ["(custom...)"] + wl_symbols,
                format_func=lambda s: wl_labels.get(s, s),
            )
            custom_sym = ""
            if symbol_choice == "(custom...)":
                custom_sym = st.text_input("Custom ticker symbol")
        with c2:
            buy_date = st.date_input("Buy date", value=date.today())
            buy_price = st.number_input(
                "Buy price (AUD per share)",
                min_value=0.0001, value=10.00, step=0.01, format="%.4f",
            )
        with c3:
            shares = st.number_input("Shares", min_value=1, value=10, step=1)
            sig_at_entry = st.selectbox(
                "TRADEON signal at the time",
                ["", "GO", "WAIT", "AVOID"],
                help=(
                    "Optional. If TRADEON had no opinion when you entered, leave blank. "
                    "Used to compute the 'beat the system' check."
                ),
            )
        c4, c5 = st.columns([1, 2])
        with c4:
            pred_pct = st.number_input(
                "TRADEON predicted % move",
                value=0.0, step=0.1, format="%.2f",
                help="Optional. Take this from the Forward Outlook 'Expected return' or Dashboard 'expected_90d_pct' at the time of entry.",
            )
            use_pred = st.checkbox("Include prediction in self-grading", value=False)
        with c5:
            notes = st.text_input("Notes (optional)")

        submitted = st.form_submit_button("Add trade", type="primary")
        if submitted:
            sym = (custom_sym or symbol_choice).strip().upper()
            t_meta = by_symbol(sym)
            try:
                entry = JournalEntry(
                    trade_id=next_trade_id(),
                    ticker=sym,
                    name=t_meta.name if t_meta else sym,
                    market=t_meta.market if t_meta else "ASX",
                    broker=broker,
                    buy_date=buy_date,
                    buy_price_aud=float(buy_price),
                    shares=int(shares),
                    tradeon_signal_at_entry=sig_at_entry,
                    tradeon_predicted_pct=float(pred_pct) if use_pred else None,
                    notes=notes,
                )
                add_entry(entry)
                st.success(f"Added trade {entry.trade_id} - {sym}.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Failed to add trade: {e}")

else:
    open_entries = [e for e in entries if e.is_open]
    if not open_entries:
        st.info("No open trades to close.")
    else:
        with st.form("close_trade", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                tid_options = {
                    f"{e.trade_id} - {e.ticker} ({e.shares} sh @ {aud(e.buy_price_aud)})": e.trade_id
                    for e in open_entries
                }
                pick = st.selectbox("Open trade", list(tid_options.keys()))
                tid = tid_options[pick]
            with c2:
                sell_date = st.date_input("Sell date", value=date.today())
            with c3:
                sell_price = st.number_input(
                    "Sell price (AUD per share)",
                    min_value=0.0001, value=10.00, step=0.01, format="%.4f",
                )
            notes_extra = st.text_input("Closing note (optional)")
            done = st.form_submit_button("Close trade", type="primary")
            if done:
                try:
                    closed = close_trade(
                        tid, sell_date, float(sell_price), notes_append=notes_extra,
                    )
                    out = compute_outcome(closed)
                    st.success(
                        f"Closed {closed.trade_id} - net after tax: "
                        f"{aud(out.net_after_tax_aud)} ({pct(out.net_pct)}) "
                        f"over {out.days_held} days."
                    )
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Failed to close trade: {e}")

st.markdown("---")

# ----- Trade history -----
st.markdown("### Trade history")

if not entries:
    st.caption("No trades yet.")
else:
    rows = []
    for e in entries:
        out = compute_outcome(e)
        rows.append({
            "ID": e.trade_id,
            "Ticker": e.ticker,
            "Buy date": e.buy_date.isoformat(),
            "Buy A$": e.buy_price_aud,
            "Shares": e.shares,
            "Invested A$": e.capital_aud,
            "Sell date": e.sell_date.isoformat() if e.sell_date else "",
            "Sell A$": e.sell_price_aud or "",
            "Days": out.days_held or "",
            "Fees A$": out.fees_aud,
            "Net A$ (after tax)": out.net_after_tax_aud or "",
            "Net %": out.net_pct,
            "TRADEON sig.": e.tradeon_signal_at_entry,
            "Pred. %": e.tradeon_predicted_pct,
            "Pred. error pp": out.prediction_error_pct,
            "Notes": e.notes,
        })
    df_hist = pd.DataFrame(rows)
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    with st.expander("Delete a trade"):
        del_pick = st.selectbox(
            "Trade to delete",
            [f"{e.trade_id} - {e.ticker} ({e.buy_date.isoformat()})" for e in entries],
            key="delete_pick",
        )
        if st.button("Delete trade", type="secondary"):
            tid_to_delete = del_pick.split(" - ")[0]
            if delete_entry(tid_to_delete):
                st.success(f"Deleted {tid_to_delete}.")
                st.rerun()

st.markdown("---")

# ----- Backup / restore -----
st.markdown("### Backup and restore")
st.caption(
    "**Important:** the journal lives in `data_cache/journal.csv`, which is "
    "**ephemeral on Streamlit Cloud's free tier** - it can be wiped by a "
    "redeploy or after the app sleeps. Download a copy regularly and upload "
    "to restore."
)

bc1, bc2 = st.columns(2)
with bc1:
    csv_bytes = export_csv().encode("utf-8")
    st.download_button(
        "Download journal as CSV",
        data=csv_bytes,
        file_name=f"tradeon_journal_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with bc2:
    uploaded = st.file_uploader("Restore from CSV", type="csv", key="journal_upload")
    if uploaded is not None:
        replace = st.checkbox(
            "Replace existing journal (otherwise merge skipping duplicates)",
            value=False,
        )
        if st.button("Import"):
            try:
                raw = uploaded.getvalue().decode("utf-8")
                n = import_csv(raw, replace=replace)
                st.success(f"Imported {n} trade(s).")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Import failed: {e}")

render_disclaimer()
