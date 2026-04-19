"""One-off profiler: where does analyse_one() time actually go?

Run: python scripts/profile_pipeline.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Avoid st.cache_data wrapper (it would cache between calls and skew the test).
# We import the inner function before the @st.cache_data decoration runs by
# monkey-patching streamlit.cache_data to be a no-op identity decorator.
import streamlit as st
st.cache_data = lambda *a, **kw: (lambda f: f)  # type: ignore[attr-defined]

from app_pipeline import analyse_one  # noqa: E402
from core.tickers import WATCHLIST  # noqa: E402

SYMBOLS = ["MSFT", "BHP.AX", "AAPL", "CBA.AX"]


def time_one(symbol: str) -> dict:
    t0 = time.perf_counter()
    res = analyse_one(symbol, broker="Stake")
    elapsed = time.perf_counter() - t0
    return {"symbol": symbol, "elapsed_s": elapsed, "ok": "error" not in res}


def main() -> None:
    print(f"Profiling analyse_one() across {len(SYMBOLS)} symbols (vanilla settings, no cache)")
    print("=" * 70)
    total = 0.0
    for sym in SYMBOLS:
        r = time_one(sym)
        status = "OK" if r["ok"] else "ERR"
        print(f"  {sym:<10} {r['elapsed_s']:6.2f}s  [{status}]")
        total += r["elapsed_s"]
    avg = total / len(SYMBOLS)
    print("-" * 70)
    print(f"  Total: {total:.2f}s  |  Avg per symbol: {avg:.2f}s")
    full_watchlist_est = avg * len(WATCHLIST)
    print(f"  Estimated full watchlist ({len(WATCHLIST)} symbols, sequential): {full_watchlist_est:.1f}s")


if __name__ == "__main__":
    main()
