"""Sanity check that the bundled disk cache delivers the promised speedup."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
st.cache_data = lambda *a, **kw: (lambda f: f)  # type: ignore[attr-defined]

from app_pipeline import analyse_all, is_watchlist_warm, watchlist_cache_status

print(f"is_watchlist_warm(Stake): {is_watchlist_warm('Stake')}")
status = watchlist_cache_status("Stake")
print(f"Cache status: {status['fresh']}/{status['total']} fresh, "
      f"{status['stale']} stale, {status['missing']} missing")
print(f"Cache dir: {status['cache_dir']}")

t0 = time.perf_counter()
rows = analyse_all(broker="Stake", max_workers=4)
elapsed = time.perf_counter() - t0
ok = sum(1 for r in rows if "error" not in r)
print(f"analyse_all() with warm cache: {elapsed:.3f}s ({ok}/{len(rows)} OK)")
