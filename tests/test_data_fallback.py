"""Regression tests for `core.data.fetch_history`'s stale-cache fallback.

Background: in v1.x the cache had a hard 36h TTL. After ~36 hours of uptime
on Streamlit Cloud, every committed parquet file was considered "stale" and
the code would refetch from yfinance, which is frequently rate-limited from
cloud platform IPs. Result: every watchlist stock would error out and the
Dashboard would render "21 of 21 failed to load".

These tests pin the new contract:
  - fresh cache -> use it (no network)
  - stale cache + yfinance succeeds -> use yfinance + refresh cache
  - stale cache + yfinance fails -> fall back to stale cache (don't crash)
  - no cache + yfinance fails -> raise
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Point CACHE_DIR at a fresh temp directory and reload the module."""
    monkeypatch.setenv("TRADEON_CACHE_DIR", str(tmp_path))
    import importlib
    from core import data
    importlib.reload(data)
    yield tmp_path, data
    importlib.reload(data)  # restore original CACHE_DIR for other tests


def _fake_history(rows: int = 5_000, *, last_close: float = 100.0) -> pd.DataFrame:
    """Build a fake price history in the canonical post-fetch shape."""
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=rows)
    return pd.DataFrame({
        "date": dates,
        "open": last_close,
        "high": last_close * 1.01,
        "low": last_close * 0.99,
        "close": last_close,
        "volume": 1_000_000,
    })


def test_fresh_cache_skips_network(tmp_cache):
    """If the cache is fresh, yfinance must not be called at all."""
    tmp_path, data = tmp_cache
    fake = _fake_history()
    cache_path = data._cache_path("FAKE", adjusted=True)
    fake.to_parquet(cache_path, index=False)
    # mtime is "now" so _is_fresh should be True.

    with patch("core.data._fetch_from_yfinance") as mock_yf:
        result = data.fetch_history("FAKE", adjusted=True)
        mock_yf.assert_not_called()
    assert len(result) == len(fake)


def test_stale_cache_falls_back_when_network_fails(tmp_cache):
    """The bug-fix scenario: stale cache + yfinance failure -> use cache."""
    tmp_path, data = tmp_cache
    fake = _fake_history(rows=4_999, last_close=42.0)
    cache_path = data._cache_path("STALE", adjusted=True)
    fake.to_parquet(cache_path, index=False)
    # Backdate the cache mtime to look 30 days old (well past TTL).
    old_ts = (pd.Timestamp.now() - pd.Timedelta(days=30)).timestamp()
    os.utime(cache_path, (old_ts, old_ts))

    def _boom(*args, **kwargs):
        raise RuntimeError("yfinance is rate-limited (simulated)")

    with patch("core.data._fetch_from_yfinance", side_effect=_boom):
        result = data.fetch_history("STALE", adjusted=True)
    # Got the stale-cached data back instead of crashing.
    assert len(result) == len(fake)
    assert result["close"].iloc[-1] == pytest.approx(42.0)


def test_stale_cache_with_successful_refetch_uses_fresh_data(tmp_cache):
    """If yfinance works, use the fresh data and refresh the cache."""
    tmp_path, data = tmp_cache
    stale = _fake_history(rows=4_999, last_close=10.0)
    fresh = _fake_history(rows=5_001, last_close=20.0)
    cache_path = data._cache_path("REFRESH", adjusted=True)
    stale.to_parquet(cache_path, index=False)
    old_ts = (pd.Timestamp.now() - pd.Timedelta(days=30)).timestamp()
    os.utime(cache_path, (old_ts, old_ts))

    with patch("core.data._fetch_from_yfinance", return_value=fresh):
        result = data.fetch_history("REFRESH", adjusted=True)
    assert len(result) == len(fresh)
    assert result["close"].iloc[-1] == pytest.approx(20.0)
    # Cache file should now reflect the fresh data.
    on_disk = pd.read_parquet(cache_path)
    assert len(on_disk) == len(fresh)


def test_no_cache_and_no_network_raises(tmp_cache):
    """Last-resort path: with no cache to fall back on, propagate the error."""
    tmp_path, data = tmp_cache
    with patch("core.data._fetch_from_yfinance", side_effect=RuntimeError("offline")):
        with pytest.raises(RuntimeError, match="offline"):
            data.fetch_history("MISSING", adjusted=True)


def test_force_refresh_still_falls_back_on_failure(tmp_cache):
    """force_refresh should also gracefully fall back if cache exists."""
    tmp_path, data = tmp_cache
    fake = _fake_history(last_close=7.0)
    cache_path = data._cache_path("FORCED", adjusted=True)
    fake.to_parquet(cache_path, index=False)
    # Even though cache is fresh, force_refresh skips the fast path.
    with patch("core.data._fetch_from_yfinance", side_effect=RuntimeError("flaky")):
        result = data.fetch_history("FORCED", adjusted=True, force_refresh=True)
    assert result["close"].iloc[-1] == pytest.approx(7.0)
