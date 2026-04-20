"""Pre-compute and bundle pipeline cache pickles for Streamlit Cloud.

Run nightly by .github/workflows/refresh-cache.yml right after the
parquet refresh. The output (`data_cache/pipeline/*.pkl`) ships with
the repo so Streamlit Cloud cold-starts the app with a fully-warm
pipeline cache — first user visit after a deploy is ~0.2 sec instead
of the otherwise 3-5 minute compute pass.

Why bundling matters
--------------------
Streamlit Community Cloud's free tier wipes the running container's
filesystem on sleep/wake AND on every redeploy. Without bundling, the
disk-pipeline cache layer is empty after every deploy and after every
~7-day idle period, defeating most of its value. By committing the
pickles into the repo (much like `data_cache/*.parquet`), they ship
with each deploy and are immediately usable by the live app.

Safety
------
- Pickles include a `CACHE_VERSION` salt (see core/pipeline_cache.py).
  If the analyse_one() return dict shape changes between when this
  script runs and when the live app loads them, the version mismatch
  is detected and the live app falls back to fresh computation. So a
  broken pickle never crashes the user — worst case is one slow load.
- After writing each pickle, the script reads it back and verifies the
  result deserialises cleanly. Any failures are reported in the manifest.
- Vanilla settings only (all toggles off). Toggle combos are user-
  specific and would multiply the bundle size by 32; we let users pay
  the recompute cost when they activate a non-default combo.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Make `app_pipeline` importable without a running Streamlit server.
# Replace @st.cache_data with a no-op decorator BEFORE we import
# app_pipeline so its module-level decoration succeeds.
import streamlit as st  # noqa: E402
st.cache_data = lambda *a, **kw: (lambda f: f)  # type: ignore[attr-defined]

from app_pipeline import analyse_one  # noqa: E402
from core.pipeline_cache import (  # noqa: E402
    CACHE_DIR,
    CACHE_VERSION,
    PIPELINE_CACHE_TTL_HOURS,
    load_cached,
    save_cached,
)
from core.tickers import WATCHLIST  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refresh_pipeline_cache")

# We bundle ONE toggle combo: vanilla (everything off). This matches the
# default state every user starts in; non-default toggle combos remain a
# per-user recompute, which is acceptable because they're opt-in.
VANILLA_TOGGLES = {
    "enh_garch": False,
    "enh_macro": False,
    "enh_regime_grade": False,
    "enh_recency_weighted": False,
    "enh_drawdown_breaker": False,
}
BROKER = "Stake"


def _refresh_one(symbol: str) -> dict:
    """Compute analyse_one(), pickle it, then read back to verify."""
    started = time.perf_counter()
    try:
        # Run the full per-stock pipeline. analyse_one writes the pickle
        # itself via save_cached() at the end, so no extra save call here.
        result = analyse_one(
            symbol, broker=BROKER, enh_label="vanilla", **VANILLA_TOGGLES,
        )
        if "error" in result:
            elapsed = time.perf_counter() - started
            log.warning("SKIP %-10s  %s  (%.1fs)", symbol, result["error"], elapsed)
            return {"symbol": symbol, "ok": False,
                    "error": result["error"], "elapsed_s": round(elapsed, 2)}

        # Belt + braces: save explicitly even though analyse_one already
        # called save_cached(). This way a future refactor of analyse_one
        # that drops the auto-save still produces a valid bundle here.
        # sync=True is critical here — the live app uses async writes
        # (daemon threads) which would die when this script exits before
        # the pickle hits disk. Tests use the same opt-in.
        save_cached(symbol, BROKER, VANILLA_TOGGLES, result, sync=True)

        # Read it back to make sure the pickle is loadable. If pickle.load
        # blows up here (e.g. a non-picklable field crept into the result
        # dict), fail this symbol loudly instead of shipping a broken file.
        roundtrip = load_cached(symbol, BROKER, VANILLA_TOGGLES)
        if roundtrip is None:
            elapsed = time.perf_counter() - started
            log.error("VERIFY FAILED %-10s  pickle did not round-trip", symbol)
            return {"symbol": symbol, "ok": False,
                    "error": "pickle round-trip returned None",
                    "elapsed_s": round(elapsed, 2)}

        elapsed = time.perf_counter() - started
        trust = roundtrip.get("trust_grade", "?")
        signal = roundtrip.get("signal", "?")
        log.info("OK   %-10s  trust=%s signal=%-5s  (%.1fs)",
                 symbol, trust, signal, elapsed)
        return {
            "symbol": symbol, "ok": True,
            "trust_grade": trust, "signal": signal,
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as e:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        log.exception("FAIL %-10s  %s  (%.1fs)", symbol, e, elapsed)
        return {"symbol": symbol, "ok": False,
                "error": str(e), "elapsed_s": round(elapsed, 2)}


def main() -> int:
    log.info("Refreshing pipeline cache into %s", CACHE_DIR)
    log.info("CACHE_VERSION=%s, TTL=%dh", CACHE_VERSION, PIPELINE_CACHE_TTL_HOURS)
    log.info("Toggles: %s, broker: %s", VANILLA_TOGGLES, BROKER)
    log.info("Watchlist size: %d", len(WATCHLIST))

    started = time.perf_counter()
    entries: list[dict] = []

    for t in WATCHLIST:
        entries.append(_refresh_one(t.symbol))

    elapsed = time.perf_counter() - started
    ok = sum(1 for e in entries if e["ok"])
    failed = len(entries) - ok

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cache_version": CACHE_VERSION,
        "ttl_hours": PIPELINE_CACHE_TTL_HOURS,
        "broker": BROKER,
        "toggles": VANILLA_TOGGLES,
        "elapsed_s": round(elapsed, 1),
        "ok_count": ok,
        "fail_count": failed,
        "entries": entries,
    }
    manifest_path = CACHE_DIR / "PIPELINE_MANIFEST.json"
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2))
        log.info("Wrote %s", manifest_path)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not write manifest: %s", e)

    log.info("Done in %.1fs.  %d OK, %d failed.", elapsed, ok, failed)

    # Non-zero only if EVERYTHING failed. One bad ticker shouldn't kill
    # the bundle — the live app handles per-symbol misses gracefully.
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
