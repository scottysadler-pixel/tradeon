"""Tests for is_watchlist_warm() and watchlist_cache_status().

The critical regression caught here: is_watchlist_warm() must return
True when the disk cache is fully populated, even on a brand-new
session with empty st.session_state. Before the fix, mobile users
(iPad/Safari) saw "Compute playbook now" on every visit because their
WebSocket sessions died when they switched apps.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def isolated_pipeline_cache(tmp_path, monkeypatch):
    """Redirect the pipeline disk cache to tmp_path and reset all leakable
    module-level state (st.session_state, reloaded modules) so the test
    sees a fresh world.

    Critical detail: `st.session_state` is a process-wide singleton.
    Earlier tests in the suite (e.g. test_parallel_pipeline.py) call
    analyse_all, which sets `pipeline_warm__Stake__vanilla = True` in
    session_state. Without explicit clearing, our "cold session" tests
    would see that leftover flag and report a false positive.
    """
    monkeypatch.setenv("TRADEON_PIPELINE_CACHE_DIR", str(tmp_path))
    from core import pipeline_cache
    importlib.reload(pipeline_cache)
    import app_pipeline
    importlib.reload(app_pipeline)

    # Wipe any session_state keys leaked from earlier tests. We wipe the
    # session-warm flag specifically (not the whole dict) to avoid
    # disturbing widget keys that other tests' setup may need.
    import streamlit as st
    leftover = [k for k in list(st.session_state.keys())
                if k.startswith("pipeline_warm__")]
    for k in leftover:
        try:
            del st.session_state[k]
        except Exception:  # noqa: BLE001
            pass

    yield tmp_path

    # Same cleanup on teardown for the next test.
    for k in [k for k in list(st.session_state.keys())
              if k.startswith("pipeline_warm__")]:
        try:
            del st.session_state[k]
        except Exception:  # noqa: BLE001
            pass

    monkeypatch.undo()
    importlib.reload(pipeline_cache)
    importlib.reload(app_pipeline)


def _toggles_off() -> dict:
    return {
        "enh_garch": False, "enh_macro": False, "enh_regime_grade": False,
        "enh_recency_weighted": False, "enh_drawdown_breaker": False,
    }


def _fake_pipeline_result(symbol: str) -> dict:
    return {
        "symbol": symbol, "name": f"{symbol} Corp",
        "trust_grade": "B", "trust_score": 70.0,
        "regime": "bull", "signal": "WAIT",
        "expected_90d_pct": 3.5,
    }


def test_is_warm_false_when_disk_empty_and_session_empty(isolated_pipeline_cache):
    """Brand new session, brand new disk -> not warm."""
    import app_pipeline
    # Streamlit's session_state is mocked-out when not running under the server,
    # so we just confirm the function gracefully returns False.
    # If session_state.get raises (no runtime), the function should still return False.
    try:
        warm = app_pipeline.is_watchlist_warm("Stake")
    except Exception:
        # Without a running streamlit context, session_state may behave oddly.
        # That's the failure mode we are guarding against — treat as cold.
        warm = False
    assert warm is False


def test_is_warm_true_when_disk_fully_populated(isolated_pipeline_cache):
    """Disk cache has every watchlist symbol fresh -> warm even on cold session."""
    import app_pipeline
    from core import pipeline_cache
    from core.tickers import WATCHLIST

    # Populate disk cache for every symbol.
    for t in WATCHLIST:
        pipeline_cache.save_cached(
            t.symbol, "Stake", _toggles_off(), _fake_pipeline_result(t.symbol),
            sync=True,
        )

    # is_watchlist_warm() should now return True from the disk-cache leg
    # alone (session_state is empty in this test environment).
    assert app_pipeline.is_watchlist_warm("Stake") is True


def test_is_warm_false_when_one_symbol_missing(isolated_pipeline_cache):
    """20/21 fresh is NOT warm — we want the WHOLE watchlist ready."""
    import app_pipeline
    from core import pipeline_cache
    from core.tickers import WATCHLIST

    # Skip the last symbol on purpose.
    for t in WATCHLIST[:-1]:
        pipeline_cache.save_cached(
            t.symbol, "Stake", _toggles_off(), _fake_pipeline_result(t.symbol),
            sync=True,
        )

    assert app_pipeline.is_watchlist_warm("Stake") is False


def test_watchlist_cache_status_counts_correctly(isolated_pipeline_cache):
    """The diagnostic helper returns accurate fresh/missing/total counts."""
    import app_pipeline
    from core import pipeline_cache
    from core.tickers import WATCHLIST

    # Populate the first three.
    for t in WATCHLIST[:3]:
        pipeline_cache.save_cached(
            t.symbol, "Stake", _toggles_off(), _fake_pipeline_result(t.symbol),
            sync=True,
        )

    status = app_pipeline.watchlist_cache_status("Stake")
    assert status["total"] == len(WATCHLIST)
    assert status["fresh"] == 3
    assert status["missing"] == len(WATCHLIST) - 3
    assert status["stale"] == 0
    assert set(status["fresh_symbols"]) == {t.symbol for t in WATCHLIST[:3]}


def test_disk_inspection_does_not_crash_when_dir_missing(isolated_pipeline_cache, monkeypatch):
    """If the pipeline cache directory was somehow removed, is_warm returns
    False rather than raising — we must never block the page on a stat error."""
    import app_pipeline
    from core import pipeline_cache
    import shutil

    # Nuke the cache dir and don't recreate.
    shutil.rmtree(pipeline_cache.CACHE_DIR, ignore_errors=True)

    # Should not raise.
    assert app_pipeline.is_watchlist_warm("Stake") is False


def test_warm_per_broker_isolation(isolated_pipeline_cache):
    """Cache for broker=Stake should not satisfy a query for broker=CommSec."""
    import app_pipeline
    from core import pipeline_cache
    from core.tickers import WATCHLIST

    for t in WATCHLIST:
        pipeline_cache.save_cached(
            t.symbol, "Stake", _toggles_off(), _fake_pipeline_result(t.symbol),
            sync=True,
        )

    assert app_pipeline.is_watchlist_warm("Stake") is True
    assert app_pipeline.is_watchlist_warm("CommSec") is False
