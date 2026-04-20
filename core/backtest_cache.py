"""Disk-persistent cache for Backtest Lab results.

Why this exists
---------------
Backtest Lab runs `core.backtest.backtest_model()` for a user-selected
(symbol, model, horizon, fold-cap) combo. Each run is ~30 sec because
it walk-forward fits the model across up to 60 historical periods.
Previously a `@st.cache_data` wrapper made the SECOND visit to the
same combo instant, but the cache lived in process memory only — any
Streamlit Cloud sleep / redeploy / restart wiped it.

This module pickles each `BacktestResult` to disk, so the cache
survives across browser sessions and (within one container's uptime
period on Streamlit Cloud) across container restarts of the live app.

Differences vs `core.pipeline_cache`
------------------------------------
- Different cache key (includes model_key, horizon, max_folds).
- BacktestResult is much smaller than the pipeline dict (~10 KB vs
  ~150 KB), so we don't need to strip any volatile fields.
- NOT bundled in the repo. The watchlist pipeline cache is bundled
  because it's hit on every cold-start; Backtest Lab is opt-in and
  the combo space is much larger (5 models × 21 stocks × 3 fold-caps
  × variable horizons). Letting the cache accumulate naturally as
  users explore is a reasonable middle ground.

Safety
------
Same `CACHE_VERSION` salt pattern as `pipeline_cache`. Bump whenever
the `BacktestResult` dataclass schema changes.
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

# Bump when the BacktestResult dataclass shape changes. Old pickles
# are then ignored on read and rewritten on next compute.
CACHE_VERSION = "v1"

try:
    BACKTEST_CACHE_TTL_HOURS = int(
        os.environ.get("TRADEON_BACKTEST_CACHE_TTL_HOURS", "168")
    )  # default 7 days — historical backtest results don't change quickly
except ValueError:
    BACKTEST_CACHE_TTL_HOURS = 168


def _resolve_cache_dir() -> Path:
    """Pick a writable directory for backtest pickles.

    Mirrors the resolver in core/pipeline_cache.py: env override →
    repo `data_cache/backtest/` → tempdir.
    """
    override = os.environ.get("TRADEON_BACKTEST_CACHE_DIR")
    candidates = [
        Path(override) if override else None,
        Path(__file__).resolve().parent.parent / "data_cache" / "backtest",
        Path(tempfile.gettempdir()) / "tradeon_backtest_cache",
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
            logger.warning("Backtest cache dir %s not writable: %s", cand, e)
    fallback = Path(tempfile.gettempdir())
    logger.error(
        "No writable backtest cache directory found; falling back to %s.",
        fallback,
    )
    return fallback


CACHE_DIR = _resolve_cache_dir()


def _key_to_filename(
    symbol: str, model_key: str, horizon: int,
    market: str, broker: str, max_folds: int,
) -> str:
    """Stable filename for a (symbol, model, horizon, market, broker, folds) tuple.

    Cache version is included in the hash so a CACHE_VERSION bump
    automatically invalidates every existing pickle.
    """
    raw = "|".join([
        f"v={CACHE_VERSION}",
        f"sym={symbol}",
        f"model={model_key}",
        f"horizon={int(horizon)}",
        f"market={market}",
        f"broker={broker}",
        f"folds={int(max_folds)}",
    ]).encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    safe_sym = symbol.replace(".", "_").replace("/", "_")
    return f"{safe_sym}_{model_key}_{horizon}d_{max_folds}f_{digest}.pkl"


def _is_fresh(path: Path, ttl_hours: int = BACKTEST_CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < ttl_hours * 3600


def load_cached(
    symbol: str, model_key: str, horizon: int,
    market: str, broker: str, max_folds: int,
    *,
    ttl_hours: int = BACKTEST_CACHE_TTL_HOURS,
) -> Any | None:
    """Try to load a cached BacktestResult. Returns None on any cache miss."""
    path = CACHE_DIR / _key_to_filename(
        symbol, model_key, horizon, market, broker, max_folds,
    )
    if not _is_fresh(path, ttl_hours=ttl_hours):
        return None
    try:
        with path.open("rb") as f:
            payload = pickle.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Backtest cache for %s/%s unreadable (%s) — deleting.",
            symbol, model_key, e,
        )
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return None

    if not isinstance(payload, dict) or payload.get("_cache_version") != CACHE_VERSION:
        return None
    return payload.get("result")


def save_cached(
    symbol: str, model_key: str, horizon: int,
    market: str, broker: str, max_folds: int,
    result: Any,
) -> None:
    """Persist a BacktestResult to disk. Best-effort; never raises."""
    if result is None:
        return
    payload = {
        "_cache_version": CACHE_VERSION,
        "_saved_at": time.time(),
        "_key": {
            "symbol": symbol, "model_key": model_key, "horizon": horizon,
            "market": market, "broker": broker, "max_folds": max_folds,
        },
        "result": result,
    }
    path = CACHE_DIR / _key_to_filename(
        symbol, model_key, horizon, market, broker, max_folds,
    )
    tmp = path.with_suffix(".pkl.tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to save backtest cache for %s/%s: %s",
                       symbol, model_key, e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def clear_backtest_cache() -> int:
    """Remove every cached backtest result. Returns count of files removed."""
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


def cache_count() -> int:
    """Cheap diagnostic: how many backtest pickles are currently cached."""
    if not CACHE_DIR.exists():
        return 0
    return sum(1 for _ in CACHE_DIR.glob("*.pkl"))
