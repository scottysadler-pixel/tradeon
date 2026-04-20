"""TRADEON landing page.

Run with: streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import streamlit as st
import os
import time

from app_pipeline import analyse_all, is_watchlist_warm, watchlist_cache_status
from core.pipeline_cache import CACHE_DIR as PIPELINE_CACHE_DIR
from core.forecast import PROPHET_AVAILABLE
from core.playbook import build as build_playbook
from core.settings import from_session as enh_from_session
from core.tickers import WATCHLIST
from ui_helpers import broker_picker, capital_input, page_setup, render_disclaimer

page_setup("TRADEON", icon="")


# region agent log
def _agent_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, object] | None = None,
    *,
    run_id: str = "pre-fix",
) -> None:
    try:
        payload = {
            "sessionId": "0c742e",
            "id": f"log_{int(time.time() * 1000)}_0c742e",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "message": message,
            "data": data or {},
        }
        log_path = os.path.join(os.path.dirname(__file__), "debug-0c742e.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# endregion

st.session_state.setdefault("mobile_speed_profile", False)
st.session_state.setdefault("mobile_speed_workers", 1)
st.session_state.setdefault("mobile_speed_folds", 8)


def _last_pipeline_cache_warm() -> str | None:
    """Return the most recent pipeline cache write timestamp in UTC."""
    mtimes = []
    if not PIPELINE_CACHE_DIR.exists():
        return None
    for p in PIPELINE_CACHE_DIR.glob("*.pkl"):
        try:
            mtimes.append(p.stat().st_mtime)
        except Exception:
            continue
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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

    st.divider()
    st.subheader("Mobile speed profile")
    st.caption(
        "Useful on iPad/low-power sessions. This caps worker threads and backtest folds "
        "so first-run compute stays responsive."
    )
    _mobile_profile = st.toggle(
        "Enable mobile speed profile",
        key="mobile_speed_profile",
        help=(
            "When enabled, the app prefers faster startup with reduced compute."
        ),
    )
    st.slider(
        "Max parallel workers",
        min_value=1,
        max_value=4,
        value=st.session_state["mobile_speed_workers"],
        key="mobile_speed_workers",
        disabled=not _mobile_profile,
    )
    st.slider(
        "Max folds per stock",
        min_value=4,
        max_value=12,
        value=st.session_state["mobile_speed_folds"],
        key="mobile_speed_folds",
        disabled=not _mobile_profile,
    )

    st.divider()
    st.caption("Quick iPad presets")
    preset_cols = st.columns(3)
    with preset_cols[0]:
        if st.button("iPad preset: 1 worker", type="secondary"):
            st.session_state["mobile_speed_profile"] = True
            st.session_state["mobile_speed_workers"] = 1
            st.session_state["mobile_speed_folds"] = 4
            st.rerun()
    with preset_cols[1]:
        if st.button("iPad preset: 2 workers", type="secondary"):
            st.session_state["mobile_speed_profile"] = True
            st.session_state["mobile_speed_workers"] = 2
            st.session_state["mobile_speed_folds"] = 8
            st.rerun()
    with preset_cols[2]:
        if st.button("iPad preset: 4 workers", type="secondary"):
            st.session_state["mobile_speed_profile"] = True
            st.session_state["mobile_speed_workers"] = 4
            st.session_state["mobile_speed_folds"] = 12
            st.rerun()

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
_watchlist_cache_status: dict[str, object] | None = None
if is_watchlist_warm(broker, enh):
    # region agent log
    _agent_log("H4", "app.py:home_warm", "home page using warm cache path", {
        "broker": broker,
        "enh": enh.short_label(),
    })
    # endregion
    with st.spinner("Loading playbook from cache..."):
        rows = analyse_all(broker=broker, enh=enh)
    _render_playbook(rows)
else:
    # region agent log
    _agent_log("H4", "app.py:home_cold", "home page entering cold path", {
        "broker": broker,
        "enh": enh.short_label(),
    })
    # endregion
    _watchlist_cache_status = watchlist_cache_status(broker, enh)
    _missing = _watchlist_cache_status["missing"] + _watchlist_cache_status["stale"]
    if _missing == _watchlist_cache_status["total"]:
        _msg = (
            "First-ever load: the system needs to compute 20 years of "
            "backtests for each of the 21 watchlist stocks. **Roughly "
            "3-5 minutes**, after which results are cached and every "
            "subsequent visit is near-instant."
        )
    else:
        _msg = (
            f"{_missing} of {_watchlist_cache_status['total']} stocks need refreshing "
            f"({_watchlist_cache_status['fresh']} already cached). Should take a minute or two."
        )
    st.info(_msg)
    if st.button("Compute playbook now", type="primary"):
        # region agent log
        _agent_log("H4", "app.py:compute_pressed", "user requested full playbook compute", {
            "broker": broker,
            "enh": enh.short_label(),
        })
        # endregion
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
    _last_warm = _last_pipeline_cache_warm()
    st.write(
        f"**Last cache warm timestamp:** "
        f"{_last_warm if _last_warm is not None else 'No warm cache on disk yet'}"
    )
    if st.session_state.get("mobile_speed_profile"):
        st.write(
            f"**Mobile speed profile:** ON (workers={st.session_state.get('mobile_speed_workers')}, "
            f"folds={st.session_state.get('mobile_speed_folds')})"
        )
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
    if _watchlist_cache_status is None:
        _watchlist_cache_status = watchlist_cache_status(broker, enh)
    _cs = _watchlist_cache_status
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
