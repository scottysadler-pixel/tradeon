"""Watchlist - manage tracked tickers and see recommender suggestions.

For now the watchlist is defined in `core/tickers.py`. This page surfaces
that, plus the recommender's top picks based on pattern strength.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.analysis import pattern_strength
from core.backtest import backtest_all, trust_grade
from core.data import cache_status, clear_cache, fetch_history
from core.fx import normalise_to_aud
from core.recommendations import rank
from core.tickers import WATCHLIST, by_symbol
from ui_helpers import grade_badge, page_setup, render_disclaimer

page_setup("Watchlist")

st.markdown(
    "The active watchlist. To permanently add or remove tickers, edit "
    "`core/tickers.py` (a future version will let you do this in the UI)."
)

st.markdown("### Current watchlist")
df_wl = pd.DataFrame([{
    "Symbol": t.symbol, "Name": t.name, "Sector": t.sector,
    "Market": t.market, "Currency": t.currency,
} for t in WATCHLIST])
st.dataframe(df_wl, hide_index=True, width="stretch")

st.markdown("### Recommender (focus your attention)")
st.caption(
    "Ranks watchlist stocks by pattern strength + earned trust grade. "
    "Highest-scoring names are the ones most worth checking the Forward "
    "Outlook for."
)


@st.cache_data(ttl=3600, show_spinner="Scoring watchlist...")
def score_all() -> tuple[dict, dict]:
    ps = {}
    tg = {}
    for t in WATCHLIST:
        try:
            raw = fetch_history(t.symbol, years=20, adjusted=True)
            df = normalise_to_aud(raw, t)
            ps[t.symbol] = pattern_strength(df)
            results = backtest_all(df, horizon_days=90, market=t.market, broker="Stake")
            tg[t.symbol] = trust_grade(results).grade
        except Exception:  # noqa: BLE001
            ps[t.symbol] = 0.0
            tg[t.symbol] = "F"
    return ps, tg


ps, tg = score_all()
recs = rank(ps, tg, top_n=8)

rows = []
for r in recs:
    rows.append({
        "Symbol": r.ticker.symbol, "Name": r.ticker.name,
        "Sector": r.ticker.sector,
        "Pattern": round(r.pattern_strength, 2),
        "Grade": r.trust_grade, "Score": round(r.score, 1),
        "Reason": r.reason,
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

st.markdown("### Cache management")
status = cache_status()
if status.empty:
    st.caption("No cached data yet.")
else:
    st.dataframe(status, hide_index=True, width="stretch")
if st.button("Clear all cached data (will refetch on next load)"):
    n = clear_cache()
    st.success(f"Deleted {n} cached files.")

render_disclaimer()
