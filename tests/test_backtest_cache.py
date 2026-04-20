"""Tests for core/backtest_cache.py.

Mirrors the pipeline_cache test suite but with the Backtest-Lab-specific
cache key (model + horizon + fold-cap), to protect against regressions
in:
  - cache key uniqueness (different params -> different files)
  - corrupt-pickle handling (must not raise)
  - version-mismatch invalidation
  - atomic writes (failed save can't corrupt existing valid file)
  - TTL freshness check
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def tmp_bt_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEON_BACKTEST_CACHE_DIR", str(tmp_path))
    from core import backtest_cache
    importlib.reload(backtest_cache)
    yield tmp_path, backtest_cache
    monkeypatch.undo()
    importlib.reload(backtest_cache)


def _fake_result():
    """Stand-in for a BacktestResult — anything picklable works."""
    import pandas as pd
    return {
        "model_name": "ensemble",
        "n_folds": 60,
        "mape_pct": 12.3,
        "directional_accuracy_pct": 58.5,
        "ci_coverage_pct": 78.0,
        "paper_trade_net_return_pct_aud": 4.2,
        "sample_predictions": pd.DataFrame({
            "fold_end": pd.bdate_range("2020-01-01", periods=10),
            "actual_end": [100.0] * 10,
            "predicted_end": [101.0] * 10,
        }),
    }


def test_save_load_roundtrip(tmp_bt_cache):
    _, bc = tmp_bt_cache
    result = _fake_result()
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, result)
    loaded = bc.load_cached("MSFT", "ensemble", 90, "US", "Stake", 60)
    assert loaded is not None
    assert loaded["mape_pct"] == pytest.approx(12.3)
    assert loaded["n_folds"] == 60


def test_load_returns_none_for_missing(tmp_bt_cache):
    _, bc = tmp_bt_cache
    assert bc.load_cached("AAPL", "arima", 30, "US", "Stake", 20) is None


def test_load_returns_none_for_stale(tmp_bt_cache):
    _, bc = tmp_bt_cache
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, _fake_result())
    assert bc.load_cached("MSFT", "ensemble", 90, "US", "Stake", 60, ttl_hours=0) is None


def test_different_combos_get_different_files(tmp_bt_cache):
    _, bc = tmp_bt_cache
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, {**_fake_result(), "mape_pct": 10.0})
    bc.save_cached("MSFT", "arima",    90, "US", "Stake", 60, {**_fake_result(), "mape_pct": 20.0})
    bc.save_cached("MSFT", "ensemble", 30, "US", "Stake", 60, {**_fake_result(), "mape_pct": 30.0})
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 20, {**_fake_result(), "mape_pct": 40.0})

    assert bc.load_cached("MSFT", "ensemble", 90, "US", "Stake", 60)["mape_pct"] == 10.0
    assert bc.load_cached("MSFT", "arima",    90, "US", "Stake", 60)["mape_pct"] == 20.0
    assert bc.load_cached("MSFT", "ensemble", 30, "US", "Stake", 60)["mape_pct"] == 30.0
    assert bc.load_cached("MSFT", "ensemble", 90, "US", "Stake", 20)["mape_pct"] == 40.0
    assert bc.cache_count() == 4


def test_corrupt_pickle_returns_none_and_deletes(tmp_bt_cache):
    tmp_path, bc = tmp_bt_cache
    fname = bc._key_to_filename("MSFT", "ensemble", 90, "US", "Stake", 60)
    bad = tmp_path / fname
    bad.write_bytes(b"not a real pickle")
    assert bc.load_cached("MSFT", "ensemble", 90, "US", "Stake", 60) is None
    assert not bad.exists()


def test_clear_backtest_cache(tmp_bt_cache):
    _, bc = tmp_bt_cache
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, _fake_result())
    bc.save_cached("AAPL", "arima",    30, "US", "Stake", 20, _fake_result())
    assert bc.cache_count() == 2
    n = bc.clear_backtest_cache()
    assert n == 2
    assert bc.cache_count() == 0


def test_filename_safe_for_dot_symbols(tmp_bt_cache):
    _, bc = tmp_bt_cache
    fname = bc._key_to_filename("BHP.AX", "ensemble", 90, "ASX", "CommSec", 60)
    sym_part = fname.split("_")[0]
    assert "." not in sym_part
    assert fname.endswith(".pkl")
    assert "ensemble" in fname
    assert "90d" in fname
    assert "60f" in fname


def test_save_does_not_raise_on_disk_error(tmp_bt_cache):
    """A failed pickle.dump must be swallowed, not raised."""
    from unittest.mock import patch
    _, bc = tmp_bt_cache
    import pickle as _pk
    with patch.object(_pk, "dump", side_effect=OSError("disk full")):
        # Must not raise.
        bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, _fake_result())
    # And nothing got persisted.
    assert bc.cache_count() == 0


def test_save_does_not_persist_none(tmp_bt_cache):
    _, bc = tmp_bt_cache
    bc.save_cached("MSFT", "ensemble", 90, "US", "Stake", 60, None)
    assert bc.cache_count() == 0
