"""End-to-end profile: full-watchlist analyse_all() before/after parallelism.

Run: python scripts/profile_full_watchlist.py

Times three scenarios:
  1. Cold parallel (4 workers, no disk cache)        -> the realistic cold-load
  2. Warm parallel (4 workers, disk cache populated) -> cold-after-sleep wake
  3. Sequential (1 worker, no disk cache)            -> the OLD behaviour
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Bypass @st.cache_data to make timings reflect the underlying work.
import streamlit as st
st.cache_data = lambda *a, **kw: (lambda f: f)  # type: ignore[attr-defined]

# Use a fresh temp directory for the disk cache so prior runs don't pollute.
CACHE_TMP = Path(tempfile.mkdtemp(prefix="tradeon_perf_"))
import os
os.environ["TRADEON_PIPELINE_CACHE_DIR"] = str(CACHE_TMP)

import importlib
from core import pipeline_cache
importlib.reload(pipeline_cache)
import app_pipeline
importlib.reload(app_pipeline)
from core.tickers import WATCHLIST  # noqa: E402


def time_run(label: str, max_workers: int, clear_disk: bool = False) -> float:
    if clear_disk:
        for p in CACHE_TMP.glob("*.pkl"):
            p.unlink()
    t0 = time.perf_counter()
    rows = app_pipeline.analyse_all(broker="Stake", max_workers=max_workers)
    elapsed = time.perf_counter() - t0
    ok = sum(1 for r in rows if "error" not in r)
    print(f"  {label:<48} {elapsed:6.1f}s  ({ok}/{len(rows)} OK)")
    return elapsed


def main() -> None:
    print(f"Profiling analyse_all() over {len(WATCHLIST)} watchlist symbols")
    print("=" * 72)

    cold_par = time_run("1. Cold parallel (4 workers, empty disk cache)", 4, clear_disk=True)
    warm_par = time_run("2. Warm parallel (4 workers, disk cache hit)", 4, clear_disk=False)

    # Sequential is slow; only run if user asks.
    if "--with-sequential" in sys.argv:
        seq = time_run("3. Sequential (1 worker, empty disk cache)", 1, clear_disk=True)
        print(f"\n  Speedup (cold): {seq / cold_par:.1f}x")

    print("=" * 72)
    print(f"  Cold parallel:  ~{cold_par:.0f}s  (the realistic cold-load on Streamlit Cloud)")
    print(f"  Warm parallel:  ~{warm_par:.1f}s  (cold-load after sleep/wake -- disk cache hit)")
    print(f"\n  Cleanup: rm -rf {CACHE_TMP}")
    shutil.rmtree(CACHE_TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
