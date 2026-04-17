"""Raw price data layer.

Pulls OHLCV from yfinance, caches to local Parquet so we don't hammer
Yahoo. Handles the known ASX `.AX` quirk where `auto_adjust=True` returns
incorrect historical prices for some ASX names prior to certain dates.

NO external predictions or analyst ratings are used or stored - only raw
price/volume data.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _resolve_cache_dir() -> Path:
    """Pick a writable cache directory.

    Preference order:
      1. $TRADEON_CACHE_DIR if set (lets cloud platforms override)
      2. <repo_root>/data_cache (the normal local case)
      3. <tempdir>/tradeon_cache (fallback for read-only deploys)
    """
    override = os.environ.get("TRADEON_CACHE_DIR")
    candidates = [
        Path(override) if override else None,
        Path(__file__).resolve().parent.parent / "data_cache",
        Path(tempfile.gettempdir()) / "tradeon_cache",
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
            logger.warning("Cache dir %s not writable: %s", cand, e)
    return Path(tempfile.gettempdir())


CACHE_DIR = _resolve_cache_dir()

# Pull this many years of history by default.
DEFAULT_LOOKBACK_YEARS = 20

# Cache TTL - if cached file is younger than this, use it.
# Default 36h is chosen so files written by the nightly cache-refresh
# GitHub Action stay fresh for the entire trading day even if the action
# runs slightly late or fails once. Override with $TRADEON_CACHE_TTL_HOURS.
try:
    CACHE_TTL_HOURS = int(os.environ.get("TRADEON_CACHE_TTL_HOURS", "36"))
except ValueError:
    CACHE_TTL_HOURS = 36


def _cache_path(symbol: str, adjusted: bool) -> Path:
    suffix = "adj" if adjusted else "raw"
    safe = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}_{suffix}.parquet"


def _is_fresh(path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=ttl_hours)


def fetch_history(
    symbol: str,
    *,
    years: int = DEFAULT_LOOKBACK_YEARS,
    adjusted: bool = True,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download and cache OHLCV history for a single symbol.

    Parameters
    ----------
    symbol : e.g. "MSFT" or "BHP.AX".
    adjusted : True for total-return analysis (dividend & split adjusted),
               False for chart display (matches what you see on Yahoo's site).
               For ASX `.AX` symbols, `False` is recommended for display
               because adjusted history can look wrong vs Yahoo's own chart.
    """
    path = _cache_path(symbol, adjusted)
    if not force_refresh and _is_fresh(path):
        try:
            return pd.read_parquet(path)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache read failed for %s, will refetch: %s", symbol, e)

    end = datetime.today()
    start = end - timedelta(days=years * 366)

    ticker = yf.Ticker(symbol)
    df = ticker.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=adjusted,
        actions=False,
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")

    df = df.reset_index()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    try:
        df.to_parquet(path, index=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write failed for %s: %s", symbol, e)
    return df


def fetch_history_both(symbol: str, *, years: int = DEFAULT_LOOKBACK_YEARS) -> dict[str, pd.DataFrame]:
    """Convenience: get adjusted (for math) AND unadjusted (for display) at once."""
    return {
        "adjusted": fetch_history(symbol, years=years, adjusted=True),
        "display":  fetch_history(symbol, years=years, adjusted=False),
    }


def clear_cache(symbol: str | None = None) -> int:
    """Delete cached parquet files. Returns count deleted."""
    pattern = "*.parquet" if symbol is None else f"{symbol.replace('.', '_')}_*.parquet"
    n = 0
    for p in CACHE_DIR.glob(pattern):
        p.unlink(missing_ok=True)
        n += 1
    return n


def cache_status() -> pd.DataFrame:
    """Inspect what's cached and how fresh."""
    rows = []
    for p in CACHE_DIR.glob("*.parquet"):
        stat = p.stat()
        rows.append(
            {
                "file": p.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "age_hours": round(
                    (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).total_seconds() / 3600,
                    2,
                ),
            }
        )
    return pd.DataFrame(rows)
