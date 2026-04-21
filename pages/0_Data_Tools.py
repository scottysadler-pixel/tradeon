"""Data Tools - pre-warm caches and manage cache lifecycle.

This page is designed to keep the app responsive on iPad:
1) Fill raw price cache in advance.
2) Precompute watchlist pipeline analysis once.
3) Reuse the same per-session mobile speed controls used by the rest of the app.
4) Build/validate/import portable cache packs.
"""
from __future__ import annotations

import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from app_pipeline import analyse_all, is_watchlist_warm, resolve_worker_count, watchlist_cache_status
from core.backtest_cache import (
    BACKTEST_CACHE_TTL_HOURS,
    CACHE_DIR as BACKTEST_CACHE_DIR,
    cache_count,
    clear_backtest_cache,
)
from core.cache_pack import (
    DEFAULT_PACK_MAX_AGE_HOURS,
    build_cache_pack_bytes,
    restore_cache_pack_bytes,
    validate_cache_pack_bytes,
)
from core.data import CACHE_TTL_HOURS, CACHE_DIR, cache_status as data_cache_status, clear_cache as clear_data_cache
from core.pipeline_cache import (
    CACHE_DIR as PIPELINE_CACHE_DIR,
    PIPELINE_CACHE_TTL_HOURS,
    clear_pipeline_cache,
)
from core.settings import from_session as enh_from_session
from core.tickers import WATCHLIST
from ui_helpers import page_setup, render_disclaimer

page_setup("Data Tools")

st.markdown(
    "Use this page to aggressively warm caches so page switches are faster and more "
    "predictable on iPad or weaker Wi‑Fi."
)

st.session_state.setdefault("mobile_speed_profile", False)
st.session_state.setdefault("mobile_speed_workers", 1)
st.session_state.setdefault("mobile_speed_folds", 8)
st.session_state.setdefault("cache_pack_consent", False)
broker = st.session_state.get("broker", "Stake")
enh = enh_from_session(st.session_state)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Mobile speed profile")
    st.caption(
        "This profile is shared by Dashboard and Forward Outlook. "
        "When enabled, worker count and fold-depth are capped."
    )
    st.toggle("Enable mobile speed profile", key="mobile_speed_profile")
    st.slider("Max parallel workers", 1, 4, key="mobile_speed_workers", disabled=not st.session_state["mobile_speed_profile"])
    st.slider("Max folds per stock", 4, 12, key="mobile_speed_folds", disabled=not st.session_state["mobile_speed_profile"])

with col_b:
    st.subheader("Runtime profile")
    st.metric("Watchlist size", len(WATCHLIST))
    st.metric(
        "Current watchlist cache",
        "Warm" if is_watchlist_warm(broker, enh) else "Cold",
    )
    st.caption(
        f"Data TTL: {CACHE_TTL_HOURS}h  |  Pipeline TTL: "
        f"{PIPELINE_CACHE_TTL_HOURS}h  |  Backtest TTL: {BACKTEST_CACHE_TTL_HOURS}h"
    )

st.markdown("---")

st.subheader("Cache health snapshot")
cs = watchlist_cache_status(broker, enh)
cols = st.columns(4)
cols[0].metric("Pipeline fresh", f"{cs['fresh']}/{cs['total']}")
cols[1].metric("Pipeline stale", cs["stale"])
cols[2].metric("Pipeline missing", cs["missing"])
cols[3].metric("Pipeline entries", cs["total"])

st.write("**Raw data cache files:**")
data_status = data_cache_status()
if data_status.empty:
    st.caption("No parquet cache files written yet.")
else:
    st.dataframe(data_status.sort_values("age_hours"), width="stretch", hide_index=True)

st.caption(f"Backtest cache entries: {cache_count()}")
st.caption(f"Pipeline cache directory: `{PIPELINE_CACHE_DIR}`")
st.caption(f"Data cache directory: `{CACHE_DIR}`")
st.caption(f"Backtest cache directory: `{BACKTEST_CACHE_DIR}`")

st.markdown("---")

st.subheader("Pre-warm operations")

if st.button("Pre-warm raw price cache now", type="secondary"):
    completed = [0]
    failed: list[str] = []
    lock = Lock()
    progress = st.progress(0.0, text="Fetching history files...")

    def _fetch_one(symbol: str):
        from core.data import fetch_history

        try:
            df = fetch_history(symbol, years=20, adjusted=True)
            return symbol, len(df), None
        except Exception as e:  # noqa: BLE001
            return symbol, 0, str(e)

    prefetch_workers = resolve_worker_count(task_count=len(WATCHLIST))
    with ThreadPoolExecutor(max_workers=prefetch_workers) as pool:
        futures = [pool.submit(_fetch_one, t.symbol) for t in WATCHLIST]
        for fut in as_completed(futures):
            symbol, _nrows, _err = fut.result()
            with lock:
                completed[0] += 1
                pct = completed[0] / len(WATCHLIST)
                progress.progress(min(1.0, pct))
            if _err is not None:
                failed.append(f"{symbol}: {_err}")

    progress.empty()
    if failed:
        st.warning(f"Pre-warm complete with {len(failed)} failures.")
    else:
        st.success("Raw data cache pre-warm complete for all watchlist symbols.")

if st.button("Pre-compute watchlist analysis now", type="primary"):
    prog = st.progress(0.0, text="Analyzing watchlist symbols...")
    rows = analyse_all(broker=broker, enh=enh, progress=prog)
    prog.empty()
    if rows:
        has_error = sum(1 for r in rows if "error" in r)
        st.success(f"Watchlist pre-computed. Rows: {len(rows)} (errors: {has_error}).")
    else:
        st.warning("No rows returned from analysis.")

st.markdown("---")

st.subheader("Cache lifecycle")
with st.expander("Clear cache stores"):
    if st.button("Clear raw price cache"):
        n = clear_data_cache()
        st.success(f"Deleted {n} files from data cache.")
    if st.button("Clear pipeline cache"):
        n = clear_pipeline_cache()
        st.success(f"Deleted {n} pipeline cache files.")
    if st.button("Clear backtest cache"):
        n = clear_backtest_cache()
        st.success(f"Deleted {n} backtest cache files.")

st.subheader("Portable cache pack")
st.caption(
    "Build a validated zip and restore it on a new session/device. "
    "This is optional and only runs when you confirm."
)
st.toggle("Enable cache pack actions for this session", key="cache_pack_consent")
if st.session_state["cache_pack_consent"]:
    if st.button("Build cache pack", type="secondary"):
        with st.spinner("Building cache pack ..."):
            payload, manifest = build_cache_pack_bytes()
            st.session_state["cache_pack_bytes"] = payload
            st.session_state["cache_pack_manifest"] = manifest
            st.success("Cache pack ready.")

    if st.session_state.get("cache_pack_bytes"):
        st.caption(
            "Tip: on iPad/Safari, this downloads as a file attachment rather than "
            "opening inline, so you can close the preview and return to TRADEON."
        )
        st.download_button(
            "Download cache pack",
            data=st.session_state["cache_pack_bytes"],
            file_name="tradeon_cache_pack.zip",
            mime="application/octet-stream",
            help="Upload this file on another session to restore cache state.",
        )
        manifest = st.session_state.get("cache_pack_manifest", {})
        if manifest:
            st.caption(
                f"Pack entries: {len(manifest.get('entries', []))} "
                f"(generated {manifest.get('generated_at_utc')})"
            )

    uploaded = st.file_uploader("Import cache pack", type=["zip"], key="tools_cache_pack_upload")
    if uploaded is not None:
        _raw = uploaded.getvalue()
        _validation = validate_cache_pack_bytes(_raw, max_age_hours=DEFAULT_PACK_MAX_AGE_HOURS)
        if not _validation["valid"]:
            st.error("Pack failed validation.")
            for _err in _validation["errors"]:
                st.warning(_err)
        else:
            if _validation.get("age_hours") is not None:
                st.caption(f"Pack age: {_validation['age_hours']}h")
            if _validation["warnings"]:
                for _warn in _validation["warnings"]:
                    st.info(_warn)
            if st.button("Apply uploaded cache pack", key="tools_apply_cache_pack"):
                _restore = restore_cache_pack_bytes(_raw)
                if _restore["ok"]:
                    st.success("Cache pack applied.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Apply failed.")
                    for _err in _restore["errors"]:
                        st.warning(_err)

render_disclaimer()

