"""Tests for the parallelized analyse_all() and disk-cache integration.

Covers:
  - analyse_all preserves WATCHLIST order despite out-of-order completion
  - max_workers=1 falls back to the sequential code path
  - per-symbol exceptions don't kill the whole run
  - disk cache hit on a second analyse_one() call (in-memory cache patched out)
"""
from __future__ import annotations

import importlib
import time
from unittest.mock import patch

import pytest


@pytest.fixture
def reload_pipeline_cache_to_tmp(tmp_path, monkeypatch):
    """Isolate the disk pipeline cache to a temp dir for these tests."""
    monkeypatch.setenv("TRADEON_PIPELINE_CACHE_DIR", str(tmp_path))
    from core import pipeline_cache
    importlib.reload(pipeline_cache)
    # Also reload app_pipeline so it picks up the new pipeline_cache reference.
    import app_pipeline
    importlib.reload(app_pipeline)
    yield tmp_path
    monkeypatch.undo()
    importlib.reload(pipeline_cache)
    importlib.reload(app_pipeline)


def test_analyse_all_preserves_watchlist_order(reload_pipeline_cache_to_tmp):
    """Even with random completion times, output rows match WATCHLIST order."""
    import random
    import app_pipeline
    from core.tickers import WATCHLIST

    call_count = {"n": 0}
    counter_lock = __import__("threading").Lock()

    def fake_analyse_one(symbol, broker="Stake", **kwargs):
        # Random sleep to randomise completion order across threads.
        time.sleep(random.uniform(0.01, 0.05))
        with counter_lock:
            call_count["n"] += 1
        return {"symbol": symbol, "name": f"{symbol} fake", "signal": "WAIT"}

    with patch.object(app_pipeline, "analyse_one", side_effect=fake_analyse_one):
        rows = app_pipeline.analyse_all(broker="Stake", max_workers=4)

    assert len(rows) == len(WATCHLIST)
    assert call_count["n"] == len(WATCHLIST)
    # Output order MUST match WATCHLIST order even though threads finished
    # in unpredictable order.
    expected = [t.symbol for t in WATCHLIST]
    actual = [r["symbol"] for r in rows]
    assert actual == expected


def test_analyse_all_sequential_with_workers_1(reload_pipeline_cache_to_tmp):
    """max_workers=1 path returns the same shape as parallel path."""
    import app_pipeline
    from core.tickers import WATCHLIST

    def fake_analyse_one(symbol, broker="Stake", **kwargs):
        return {"symbol": symbol, "name": f"{symbol} fake", "signal": "WAIT"}

    with patch.object(app_pipeline, "analyse_one", side_effect=fake_analyse_one):
        rows = app_pipeline.analyse_all(broker="Stake", max_workers=1)

    assert len(rows) == len(WATCHLIST)
    assert all("error" not in r for r in rows)


def test_analyse_all_isolates_per_symbol_failure(reload_pipeline_cache_to_tmp):
    """If one symbol blows up, the others still complete and return."""
    import app_pipeline
    from core.tickers import WATCHLIST

    bad_symbol = WATCHLIST[3].symbol

    def fake_analyse_one(symbol, broker="Stake", **kwargs):
        if symbol == bad_symbol:
            raise RuntimeError("simulated yfinance outage for one ticker")
        return {"symbol": symbol, "name": f"{symbol} fake", "signal": "WAIT"}

    with patch.object(app_pipeline, "analyse_one", side_effect=fake_analyse_one):
        rows = app_pipeline.analyse_all(broker="Stake", max_workers=4)

    assert len(rows) == len(WATCHLIST)
    by_sym = {r["symbol"]: r for r in rows}
    assert "error" in by_sym[bad_symbol]
    assert "simulated yfinance outage" in by_sym[bad_symbol]["error"]
    # Every OTHER symbol succeeded.
    for t in WATCHLIST:
        if t.symbol == bad_symbol:
            continue
        assert "error" not in by_sym[t.symbol]


def test_disk_cache_skips_recompute_on_second_analyse_one(reload_pipeline_cache_to_tmp):
    """The disk cache layer should serve the second call without re-running
    the heavy backtest path."""
    import app_pipeline
    from core import pipeline_cache

    # Plant a cached result for MSFT at vanilla settings.
    toggles = {
        "enh_garch": False, "enh_macro": False, "enh_regime_grade": False,
        "enh_recency_weighted": False, "enh_drawdown_breaker": False,
    }
    fake_result = {
        "symbol": "MSFT", "name": "Microsoft", "sector": "Tech", "market": "US",
        "ticker": None, "spot_aud": 600.0,
        "trust_grade": "A", "trust_score": 85.0, "grade": None,
        "regime": "bull", "regime_obj": None,
        "signal": "GO", "signal_obj": None, "signal_headline": "synthetic",
        "expected_90d_pct": 7.3, "forecast": None, "naive": None,
        "stops": None, "hold": None, "earnings": None, "technicals": None,
        "ensemble_directional_pct": 60.0, "naive_directional_pct": 50.0,
        "hold_window": "(none)", "enhancements": None,
        "vol": None, "macro": None, "regime_grade_obj": None,
        "backtest": None, "recency_weights": None, "breaker": None,
    }
    pipeline_cache.save_cached("MSFT", "Stake", toggles, fake_result, sync=True)

    # Patch the heavy stages so we can detect if they're called.
    backtest_calls = {"n": 0}
    def boom(*a, **kw):
        backtest_calls["n"] += 1
        raise AssertionError("backtest_all should NOT be called when disk cache is hit")

    # Also need to provide a working fetch_history / normalise_to_aud so the
    # cache-hit code path can re-attach `df`. Use a minimal synthetic df.
    import pandas as pd
    # Pandas 3.x's bdate_range can return periods-1 dates; derive n after.
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=100)
    n = len(dates)
    fake_df = pd.DataFrame({
        "date": dates,
        "close": [100.0] * n,
        "open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
        "volume": [1_000_000] * n,
    })

    # Bypass @st.cache_data to test the underlying function directly.
    inner = app_pipeline.analyse_one.__wrapped__ if hasattr(app_pipeline.analyse_one, "__wrapped__") else app_pipeline.analyse_one

    with patch.object(app_pipeline, "fetch_history", return_value=fake_df), \
         patch.object(app_pipeline, "normalise_to_aud", return_value=fake_df), \
         patch.object(app_pipeline, "backtest_all", side_effect=boom):
        result = inner("MSFT", broker="Stake")

    assert backtest_calls["n"] == 0, "Heavy path was invoked despite cache hit"
    assert result["symbol"] == "MSFT"
    assert result["trust_grade"] == "A"
    assert result["expected_90d_pct"] == pytest.approx(7.3)
    # df was re-attached on cache hit (length matches our synthetic frame).
    assert "df" in result and len(result["df"]) == n
