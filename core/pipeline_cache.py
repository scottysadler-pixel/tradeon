"""Disk-persistent cache for `app_pipeline.analyse_one()` results.

Why this exists
---------------
Streamlit's `@st.cache_data` is **in-memory only**. When the app sleeps
(7-day idle on the free tier) or redeploys, the cache is gone — the next
visitor pays the full ~7-minute watchlist cold-load. This module pickles
each pipeline result to disk under `data_cache/pipeline/`, so warm starts
after a sleep are near-instant (file read + unpickle is milliseconds).

What gets cached
----------------
The full dict returned by `analyse_one()`, keyed on:
    (symbol, broker, enh_garch, enh_macro, enh_regime_grade,
     enh_recency_weighted, enh_drawdown_breaker, code_version)

The `code_version` salt is critical: it forces the cache to invalidate
after a code change so we don't deserialise pickles whose dataclass
schemas no longer match the live code. Bump `CACHE_VERSION` whenever
any field is added/removed/renamed in `analyse_one()`'s return dict.

The price DataFrame (`df`) is the single biggest field (~5 MB). We
**don't** pickle it — instead we re-fetch it on cache hit (which is
~40 ms thanks to the existing parquet cache in `core.data`). This keeps
each pickle to ~50-100 KB, so the full 21-stock cache is ~1-2 MB.

TTL and safety
--------------
- Default TTL: 24 hours. Override via `$TRADEON_PIPELINE_CACHE_TTL_HOURS`.
- All errors are caught and logged — a corrupt pickle never crashes the
  app, it just falls through to a fresh recompute.
- Cache is keyed by version, so a deploy with code changes invalidates
  every entry. No need to manually clear after upgrades.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bump this any time the shape of analyse_one's return dict changes
# (new field, renamed field, altered dataclass schema, etc.). Old pickles
# will then be ignored on read and rewritten on next compute.
CACHE_VERSION = "v1"

# How long a cached entry is considered fresh. Override via env var.
try:
    PIPELINE_CACHE_TTL_HOURS = int(
        os.environ.get("TRADEON_PIPELINE_CACHE_TTL_HOURS", "24")
    )
except ValueError:
    PIPELINE_CACHE_TTL_HOURS = 24

# Field that is intentionally NOT pickled — it's large (~5 MB) and trivially
# regenerated from the existing parquet cache via core.data.fetch_history.
# `analyse_one` re-attaches it on cache hit before returning.
_VOLATILE_FIELDS = ("df",)


def _resolve_pipeline_cache_dir() -> Path:
    """Pick a writable directory for pipeline pickles.

    Mirrors `core.data._resolve_cache_dir`'s logic (env override → repo
    `data_cache/pipeline/` → tempdir) so behaviour is consistent across
    Streamlit Cloud, local, and locked-down hosts.
    """
    override = os.environ.get("TRADEON_PIPELINE_CACHE_DIR")
    candidates = [
        Path(override) if override else None,
        Path(__file__).resolve().parent.parent / "data_cache" / "pipeline",
        Path(tempfile.gettempdir()) / "tradeon_pipeline_cache",
    ]
    for cand in candidates:
        if cand is None:
            continue
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
            return cand
        except Exception as e:  # noqa: BLE001
            logger.warning("Pipeline cache dir %s not writable: %s", cand, e)
    fallback = Path(tempfile.gettempdir())
    logger.error(
        "No writable pipeline cache directory found; falling back to %s. "
        "Subsequent cache writes will likely fail.",
        fallback,
    )
    return fallback


CACHE_DIR = _resolve_pipeline_cache_dir()


def _key_to_filename(symbol: str, broker: str, toggles: dict[str, bool]) -> str:
    """Stable filename for a (symbol, broker, toggle-combo) tuple.

    Pre-hash version so old pickles are ignored after a CACHE_VERSION bump.
    The toggle dict is sorted-by-key before hashing so identical toggle
    combos always produce identical filenames regardless of dict ordering.
    """
    parts = [
        f"v={CACHE_VERSION}",
        f"sym={symbol}",
        f"br={broker}",
    ]
    for k in sorted(toggles):
        parts.append(f"{k}={int(bool(toggles[k]))}")
    raw = "|".join(parts).encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    safe_sym = symbol.replace(".", "_").replace("/", "_")
    return f"{safe_sym}_{digest}.pkl"


def _is_fresh(path: Path, ttl_hours: int = PIPELINE_CACHE_TTL_HOURS) -> bool:
    """True if the file exists and is younger than `ttl_hours`."""
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < ttl_hours * 3600


def load_cached(
    symbol: str,
    broker: str,
    toggles: dict[str, bool],
    *,
    ttl_hours: int = PIPELINE_CACHE_TTL_HOURS,
) -> dict[str, Any] | None:
    """Try to load a cached pipeline result.

    Returns None on any cache miss (file missing, stale, corrupt, version
    mismatch). The caller should then recompute and call `save_cached`.

    The returned dict will NOT contain `df` — caller should re-attach it
    via `core.data.fetch_history` (which is itself parquet-cached and
    fast). This keeps pickle sizes small and prices always fresh.
    """
    path = CACHE_DIR / _key_to_filename(symbol, broker, toggles)
    if not _is_fresh(path, ttl_hours=ttl_hours):
        return None
    try:
        with path.open("rb") as f:
            payload = pickle.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Pipeline cache for %s unreadable (%s) — deleting and recomputing.",
            symbol, e,
        )
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return None

    if not isinstance(payload, dict) or payload.get("_cache_version") != CACHE_VERSION:
        logger.info(
            "Pipeline cache for %s has wrong version (have %r, want %r) — recomputing.",
            symbol, payload.get("_cache_version") if isinstance(payload, dict) else None,
            CACHE_VERSION,
        )
        return None

    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    return result


def save_cached(
    symbol: str,
    broker: str,
    toggles: dict[str, bool],
    result: dict[str, Any],
) -> None:
    """Persist a pipeline result to disk for the next session.

    Strips the volatile `df` field before pickling (re-fetched cheaply on
    load). All errors are swallowed — caching is best-effort, never let
    a write failure crash a live page.
    """
    if not isinstance(result, dict):
        return
    if "error" in result:
        return
    # Shallow copy so we don't mutate the caller's dict.
    persisted = {k: v for k, v in result.items() if k not in _VOLATILE_FIELDS}
    payload = {
        "_cache_version": CACHE_VERSION,
        "_saved_at": time.time(),
        "result": persisted,
    }
    path = CACHE_DIR / _key_to_filename(symbol, broker, toggles)
    tmp = path.with_suffix(".pkl.tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to save pipeline cache for %s: %s", symbol, e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def clear_pipeline_cache() -> int:
    """Remove every pickled pipeline result. Returns count of files removed.

    Useful for the Watchlist page's "Clear cache" button and for tests.
    """
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for p in CACHE_DIR.glob("*.pkl"):
        try:
            p.unlink()
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def cache_status(
    symbols: list[str],
    broker: str,
    toggles: dict[str, bool],
    *,
    ttl_hours: int = PIPELINE_CACHE_TTL_HOURS,
) -> dict[str, Any]:
    """Inspect disk-cache freshness for a list of symbols.

    Returns a dict like:
        {
            "fresh":    14,                       # how many of len(symbols) are fresh
            "stale":    5,                        # exist on disk but past TTL
            "missing":  2,                        # never saved
            "total":    21,
            "fresh_symbols":   [...],             # for diagnostics
            "missing_symbols": [...],
        }

    Used by:
      - `app_pipeline.is_watchlist_warm()` — to detect a usable disk cache
        across browser sessions.
      - The home-page "Engine status" expander — to surface cache health
        to the user so they understand why a load is fast or slow.
    """
    fresh, stale, missing = [], [], []
    for sym in symbols:
        path = CACHE_DIR / _key_to_filename(sym, broker, toggles)
        if not path.exists():
            missing.append(sym)
        elif _is_fresh(path, ttl_hours=ttl_hours):
            fresh.append(sym)
        else:
            stale.append(sym)
    return {
        "fresh": len(fresh),
        "stale": len(stale),
        "missing": len(missing),
        "total": len(symbols),
        "fresh_symbols": fresh,
        "stale_symbols": stale,
        "missing_symbols": missing,
        "cache_dir": str(CACHE_DIR),
    }
