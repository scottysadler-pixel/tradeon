"""Tests for the disk-persistent pipeline cache.

Covers:
  - save then load round-trip preserves the result minus volatile fields
  - stale entries (past TTL) are not returned
  - corrupt pickles are handled (not raised) and removed
  - schema version mismatch ignores the file
  - different toggle combos get different cache slots
  - clear_pipeline_cache wipes the directory
"""
from __future__ import annotations

import importlib
import time
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_pipeline_cache(tmp_path, monkeypatch):
    """Redirect the pipeline cache to a temp dir, isolated per test."""
    monkeypatch.setenv("TRADEON_PIPELINE_CACHE_DIR", str(tmp_path))
    from core import pipeline_cache
    importlib.reload(pipeline_cache)
    yield tmp_path, pipeline_cache
    monkeypatch.undo()
    importlib.reload(pipeline_cache)


def _sample_result(symbol: str = "MSFT") -> dict:
    """Realistic-shaped analyse_one return dict (df field intentionally large)."""
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "trust_grade": "B",
        "trust_score": 72.5,
        "regime": "bull",
        "signal": "WAIT",
        "expected_90d_pct": 4.2,
        "df": [0] * 5000,  # stand-in for the ~5MB price DataFrame
        "ensemble_directional_pct": 58.3,
    }


def _toggles_off() -> dict:
    return {
        "enh_garch": False, "enh_macro": False, "enh_regime_grade": False,
        "enh_recency_weighted": False, "enh_drawdown_breaker": False,
    }


def test_save_load_roundtrip_strips_volatile_fields(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    res = _sample_result()
    pc.save_cached("MSFT", "Stake", _toggles_off(), res)
    loaded = pc.load_cached("MSFT", "Stake", _toggles_off())
    assert loaded is not None
    assert loaded["symbol"] == "MSFT"
    assert loaded["trust_grade"] == "B"
    assert loaded["expected_90d_pct"] == pytest.approx(4.2)
    # df is intentionally not pickled — the live caller re-attaches it.
    assert "df" not in loaded


def test_load_returns_none_for_missing_entry(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    assert pc.load_cached("AAPL", "Stake", _toggles_off()) is None


def test_load_returns_none_for_stale_entry(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    pc.save_cached("MSFT", "Stake", _toggles_off(), _sample_result())
    # Entry was saved but TTL of 0 makes everything stale.
    assert pc.load_cached("MSFT", "Stake", _toggles_off(), ttl_hours=0) is None


def test_save_skips_error_results(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    bad = {"symbol": "FOO", "error": "no data"}
    pc.save_cached("FOO", "Stake", _toggles_off(), bad)
    assert pc.load_cached("FOO", "Stake", _toggles_off()) is None


def test_different_toggles_get_different_cache_slots(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    vanilla = _toggles_off()
    with_garch = {**vanilla, "enh_garch": True}

    pc.save_cached("MSFT", "Stake", vanilla, {**_sample_result(), "trust_score": 50.0})
    pc.save_cached("MSFT", "Stake", with_garch, {**_sample_result(), "trust_score": 80.0})

    a = pc.load_cached("MSFT", "Stake", vanilla)
    b = pc.load_cached("MSFT", "Stake", with_garch)
    assert a is not None and a["trust_score"] == 50.0
    assert b is not None and b["trust_score"] == 80.0


def test_different_brokers_get_different_cache_slots(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    pc.save_cached("MSFT", "Stake", _toggles_off(), {**_sample_result(), "trust_score": 60.0})
    pc.save_cached("MSFT", "CommSec", _toggles_off(), {**_sample_result(), "trust_score": 65.0})
    a = pc.load_cached("MSFT", "Stake", _toggles_off())
    b = pc.load_cached("MSFT", "CommSec", _toggles_off())
    assert a["trust_score"] == 60.0
    assert b["trust_score"] == 65.0


def test_corrupt_pickle_returns_none_and_deletes_file(tmp_pipeline_cache):
    tmp_path, pc = tmp_pipeline_cache
    # Write garbage bytes at the expected filename.
    fname = pc._key_to_filename("MSFT", "Stake", _toggles_off())
    bad_path = tmp_path / fname
    bad_path.write_bytes(b"not a real pickle, just garbage")
    # Should not raise, just return None and remove the bad file.
    assert pc.load_cached("MSFT", "Stake", _toggles_off()) is None
    assert not bad_path.exists()


def test_version_mismatch_returns_none(tmp_pipeline_cache):
    tmp_path, pc = tmp_pipeline_cache
    # Save normally then patch the module's CACHE_VERSION so reading sees a mismatch.
    pc.save_cached("MSFT", "Stake", _toggles_off(), _sample_result())
    fname = pc._key_to_filename("MSFT", "Stake", _toggles_off())
    saved = (tmp_path / fname).exists()
    assert saved
    with patch.object(pc, "CACHE_VERSION", "v999"):
        # The filename hash changes with version, so old file isn't even targeted.
        # But also: a stale file from the old version is silently skipped.
        assert pc.load_cached("MSFT", "Stake", _toggles_off()) is None


def test_clear_pipeline_cache_removes_all_pickles(tmp_pipeline_cache):
    _, pc = tmp_pipeline_cache
    pc.save_cached("MSFT", "Stake", _toggles_off(), _sample_result("MSFT"))
    pc.save_cached("BHP.AX", "Stake", _toggles_off(), _sample_result("BHP.AX"))
    pc.save_cached("AAPL", "Stake", _toggles_off(), _sample_result("AAPL"))
    n = pc.clear_pipeline_cache()
    assert n == 3
    # All gone.
    assert pc.load_cached("MSFT", "Stake", _toggles_off()) is None
    assert pc.load_cached("BHP.AX", "Stake", _toggles_off()) is None


def test_filename_safe_for_dot_symbols(tmp_pipeline_cache):
    """ASX symbols like BHP.AX must produce filesystem-safe filenames."""
    _, pc = tmp_pipeline_cache
    fname = pc._key_to_filename("BHP.AX", "Stake", _toggles_off())
    # No dots in the symbol portion (they're replaced with underscores).
    sym_part = fname.split("_")[0]
    assert "." not in sym_part
    assert fname.endswith(".pkl")


def test_save_is_atomic_via_tmp_file(tmp_pipeline_cache):
    """A failed pickle.dump must not leave a half-written .pkl behind."""
    tmp_path, pc = tmp_pipeline_cache
    res = _sample_result()
    # First do a real save so we have a valid file to check non-corruption against.
    pc.save_cached("MSFT", "Stake", _toggles_off(), res)
    fname = pc._key_to_filename("MSFT", "Stake", _toggles_off())
    pkl_path = tmp_path / fname
    original_bytes = pkl_path.read_bytes()

    # Now simulate a write failure mid-save: monkeypatch pickle.dump to raise.
    import pickle as _pk
    with patch.object(_pk, "dump", side_effect=OSError("disk full")):
        # Should not raise — best-effort save.
        pc.save_cached("MSFT", "Stake", _toggles_off(), {**res, "trust_score": 99.0})

    # File still has the original valid bytes; the failed write didn't clobber it.
    assert pkl_path.read_bytes() == original_bytes
    # And no leftover .pkl.tmp.
    assert not (tmp_path / (fname + ".tmp")).exists()
    assert not pkl_path.with_suffix(".pkl.tmp").exists()
