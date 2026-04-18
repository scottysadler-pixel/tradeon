"""Refresh the on-disk price cache for the bundled deployment.

Run nightly by the GitHub Action in .github/workflows/refresh-cache.yml.
Can also be invoked locally any time with:

    python scripts/refresh_cache.py

What it does
------------
1. Force-refreshes 20 years of OHLCV history for every symbol the app
   touches: the watchlist, the AUD/USD FX pair, the parent indices used
   by the macro-confirmation enhancement (^GSPC, ^AXJO), and ^VIX.
2. Writes them to ``data_cache/*.parquet`` (the same files the running
   app reads from), so a Streamlit Cloud cold start that clones the
   repo gets pre-warmed cache instantly.
3. Drops a ``data_cache/MANIFEST.json`` next to them with a build
   timestamp and per-symbol metadata so we can tell at a glance how
   stale the bundled snapshot is.

Failures on individual symbols are logged but do not abort the run -
yfinance is occasionally flaky and we'd rather refresh 23/24 symbols
than refresh nothing.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make `core` importable when run as a top-level script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.data import CACHE_DIR, fetch_history  # noqa: E402
from core.tickers import WATCHLIST  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refresh_cache")


# (symbol, years, adjusted) tuples to fetch.
# Mirrors what the running app actually reads:
#   * Watchlist  -> adjusted=True, 20y    (analyse_one)
#   * AUDUSD=X   -> adjusted=False, 25y   (core/fx.py)
#   * ^GSPC      -> adjusted=True, 10y    (core/macro.py for US)
#   * ^AXJO     -> adjusted=True, 10y    (core/macro.py for ASX)
#   * ^VIX       -> adjusted=False, 1y    (core/macro.py)
EXTRA_FETCHES: list[tuple[str, int, bool]] = [
    ("AUDUSD=X", 25, False),
    ("^GSPC",    10, True),
    ("^AXJO",    10, True),
    ("^VIX",      1, False),
]


def _fetch_one(symbol: str, years: int, adjusted: bool) -> dict:
    """Force-refresh one symbol; return a manifest entry.

    Crucially passes `allow_stale_fallback=False` so a yfinance failure
    actually fails this symbol instead of being silently masked by the
    existing cache file - otherwise the MANIFEST.json would lie about
    successful refreshes.
    """
    started = time.perf_counter()
    try:
        df = fetch_history(
            symbol,
            years=years,
            adjusted=adjusted,
            force_refresh=True,
            allow_stale_fallback=False,
        )
        elapsed = time.perf_counter() - started
        first = df["date"].iloc[0].strftime("%Y-%m-%d") if len(df) else None
        last = df["date"].iloc[-1].strftime("%Y-%m-%d") if len(df) else None
        log.info("OK   %-10s  %5d rows  %s -> %s  (%.1fs)",
                 symbol, len(df), first, last, elapsed)
        return {
            "symbol": symbol,
            "ok": True,
            "rows": int(len(df)),
            "first_date": first,
            "last_date": last,
            "adjusted": adjusted,
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as e:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        log.warning("FAIL %-10s  %s  (%.1fs)", symbol, e, elapsed)
        return {
            "symbol": symbol,
            "ok": False,
            "error": str(e),
            "adjusted": adjusted,
            "elapsed_s": round(elapsed, 2),
        }


def main() -> int:
    log.info("Refreshing TRADEON cache into %s", CACHE_DIR)

    started = time.perf_counter()
    entries: list[dict] = []

    for t in WATCHLIST:
        entries.append(_fetch_one(t.symbol, years=20, adjusted=True))
        # Be polite to Yahoo - small jitter between calls.
        time.sleep(0.4)

    for symbol, years, adjusted in EXTRA_FETCHES:
        entries.append(_fetch_one(symbol, years=years, adjusted=adjusted))
        time.sleep(0.4)

    elapsed = time.perf_counter() - started
    ok = sum(1 for e in entries if e["ok"])
    failed = len(entries) - ok

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "ok_count": ok,
        "fail_count": failed,
        "entries": entries,
    }
    manifest_path = CACHE_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Wrote %s", manifest_path)
    log.info("Done in %.1fs.  %d OK, %d failed.", elapsed, ok, failed)

    # Exit non-zero only if EVERYTHING failed - one bad symbol shouldn't
    # break the GitHub Action and prevent committing the rest.
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
