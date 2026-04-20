"""TRADEON landing page.

Run with: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from app_pipeline import analyse_all, is_watchlist_warm, watchlist_cache_status
from core.forecast import PROPHET_AVAILABLE
from core.playbook import build as build_playbook
from core.settings import from_session as enh_from_session
from core.tickers import WATCHLIST
from ui_helpers import broker_picker, capital_input, page_setup, render_disclaimer

page_setup("TRADEON", icon="")

st.markdown(
    "##### Self-validating stock outlook for an Australian retail trader. "
    "All projections computed locally from raw historical price data."
)

with st.sidebar:
    st.header("Settings")
    broker = broker_picker()
    capital = capital_input()
    st.caption(f"Watchlist: **{len(WATCHLIST)}** stocks")
    st.session_state["broker"] = broker
    # Note: capital_input() uses widget key "capital", which auto-populates
    # st.session_state["capital"]. Re-assigning it here would raise
    # StreamlitAPIException ("widget already created with this key").

    enh = enh_from_session(st.session_state)
    if enh.any_active():
        st.markdown("**Active enhancements:**")
        st.caption(f"`{enh.short_label()}`")
        st.caption("Adjust in the Strategy Lab page.")
    else:
        st.caption("No enhancements active. Visit **Strategy Lab** to experiment.")

# ----- Today's Playbook -----
st.markdown("### Today's playbook")

_PLAYBOOK_BANNER_COLORS = {
    "go":    ("#22c55e", "#0b1220"),
    "wait":  ("#94a3b8", "#0b1220"),
    "avoid": ("#ef4444", "#ffffff"),
    "info":  ("#3b82f6", "#ffffff"),
}

def _render_playbook(rows):
    pb = build_playbook(rows)
    bg, fg = _PLAYBOOK_BANNER_COLORS.get(pb.headline.accent, ("#94a3b8", "#0b1220"))
    st.markdown(
        f"<div style='background:{bg};color:{fg};padding:14px 18px;"
        f"border-radius:10px;margin-bottom:8px'>"
        f"<div style='font-weight:700;font-size:1.05em'>{pb.headline.title}</div>"
        f"<div style='margin-top:6px'>{pb.headline.body}</div></div>",
        unsafe_allow_html=True,
    )
    pcols = st.columns(2)
    with pcols[0]:
        st.markdown("**Watchlist mood**")
        st.markdown(pb.mood.description)
        st.caption(
            f"Bull: {pb.mood.bull} | Bear: {pb.mood.bear} | "
            f"Sideways: {pb.mood.sideways}"
        )
    with pcols[1]:
        st.markdown("**One to watch**")
        if pb.watch:
            st.markdown(pb.watch.text)
        else:
            st.caption("No standout seasonal windows on the watchlist right now.")
    st.caption(f"Generated {pb.generated_at.strftime('%a %d %b %Y, %H:%M')}")


# Auto-load when the disk cache is warm. is_watchlist_warm() now checks
# both session_state AND the on-disk pipeline cache, so a fresh browser
# session (e.g. iPad after switching apps) still picks up the cached
# results in ~0.2 sec instead of showing "Compute now" pointlessly.
if is_watchlist_warm(broker, enh):
    with st.spinner("Loading playbook from cache..."):
        rows = analyse_all(broker=broker, enh=enh)
    _render_playbook(rows)
else:
    _status = watchlist_cache_status(broker, enh)
    _missing = _status["missing"] + _status["stale"]
    if _missing == _status["total"]:
        _msg = (
            "First-ever load: the system needs to compute 20 years of "
            "backtests for each of the 21 watchlist stocks. **Roughly "
            "3-5 minutes**, after which results are cached and every "
            "subsequent visit is near-instant."
        )
    else:
        _msg = (
            f"{_missing} of {_status['total']} stocks need refreshing "
            f"({_status['fresh']} already cached). Should take a minute or two."
        )
    st.info(_msg)
    if st.button("Compute playbook now", type="primary"):
        prog = st.progress(0.0, text="Crunching watchlist...")
        analyse_all(broker=broker, progress=prog, enh=enh)
        prog.empty()
        st.rerun()

st.markdown("---")
st.markdown("### Welcome")
st.markdown(
    """
    TRADEON looks at 20 years of raw price history for an Australian-tilted watchlist
    of prominent stocks (ASX large caps + a few US big-tech names) and runs an
    in-house ensemble of forecasting models. Every prediction is graded against what
    really happened - we earn your trust BEFORE issuing any recommendations.

    **Default state for every stock is WAIT.** A green GO signal only appears when
    multiple independent indicators agree. Most days you'll see no green lights -
    that is the system protecting you from low-quality trades.
    """
)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("####  Get started")
    st.markdown(
        "1. Open the **Dashboard** to see today's status across the watchlist.\n"
        "2. Click into a stock on **Deep Dive** to see its 20-year analysis.\n"
        "3. Check **Forward Outlook** for active GO signals."
    )
with col2:
    st.markdown("####  How honest is it?")
    st.markdown(
        "Every metric is reported BOTH on its own AND vs a naive 'tomorrow = today' "
        "baseline. If our ensemble doesn't beat the naive baseline on a stock, the "
        "trust grade drops to D or F and we ignore it."
    )
with col3:
    st.markdown("####  New to investing?")
    st.markdown(
        "Visit the **Learn** page for plain-English explainers on broker accounts, "
        "order types, settlement, AU CGT, dividends, and a glossary of every metric "
        "used in the app."
    )

st.markdown("---")

with st.expander("Engine status"):
    import sys
    st.write(f"**Python:** {sys.version.split()[0]}")
    st.write(f"**Prophet available:** {'Yes' if PROPHET_AVAILABLE else 'No (fallback to Holt-Winters + ARIMA)'}")
    st.write(f"**Watchlist size:** {len(WATCHLIST)} stocks")
    if not PROPHET_AVAILABLE:
        st.caption(
            "Prophet isn't installed in this environment, so the ensemble runs on "
            "Holt-Winters + ARIMA. Forecasts still work; accuracy on big-tech names "
            "is slightly lower than with Prophet enabled. To add Prophet locally, "
            "use Python 3.11/3.12 and run `pip install prophet`. On Streamlit "
            "Community Cloud, Prophet installs automatically (Python 3.11 is pinned "
            "via runtime.txt)."
        )

    st.markdown("---")
    st.markdown("**Pipeline cache health**")
    _cs = watchlist_cache_status(broker, enh)
    _emoji = "OK" if _cs["fresh"] == _cs["total"] else "WARM" if _cs["fresh"] > 0 else "COLD"
    st.write(
        f"`{_emoji}`  **{_cs['fresh']}/{_cs['total']}** stocks fresh on disk  "
        f"(stale: {_cs['stale']}, missing: {_cs['missing']})"
    )
    if _cs["fresh"] == _cs["total"]:
        st.caption(
            "All 21 stocks are cached on disk and fresh — every page in the "
            "app will load in under a second. Cache auto-refreshes every "
            "24 hours, or whenever the nightly GitHub Action redeploys."
        )
    elif _cs["missing"] == _cs["total"]:
        st.caption(
            "Disk cache is empty. This usually happens after a Streamlit Cloud "
            "redeploy or a long sleep. The next analysis pass will populate it; "
            "every subsequent visit (until the next deploy) will be instant. "
            "On Streamlit Cloud, the bundled cache from the nightly GitHub "
            "Action is normally already populated on deploy — if it's empty "
            "here, the action may not have run yet for this commit."
        )
    else:
        if _cs["missing_symbols"]:
            st.caption(f"Missing: {', '.join(_cs['missing_symbols'][:8])}"
                       + (" ..." if len(_cs["missing_symbols"]) > 8 else ""))
        if _cs["stale_symbols"]:
            st.caption(f"Stale (will refresh on next load): "
                       f"{', '.join(_cs['stale_symbols'][:8])}"
                       + (" ..." if len(_cs["stale_symbols"]) > 8 else ""))

render_disclaimer()
