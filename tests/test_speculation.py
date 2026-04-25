"""Unit tests for the speculative prediction register and outcome math."""

from __future__ import annotations

from datetime import date

import pytest

import core.speculation as spec


def _build_prediction(pred_id: str, direction: str) -> spec.SpeculationPrediction:
    return spec.SpeculationPrediction(
        prediction_id=pred_id,
        created_at="2026-04-10",
        symbol="MSFT",
        name="Microsoft",
        market="NASDAQ",
        direction=direction,  # type: ignore[arg-type]
        broker="Stake",
        capital_aud=1000.0,
        horizon_days=30,
        entry_price_aud=100.0,
        expected_return_pct=-10.0 if direction == "SHORT" else 10.0,
        predicted_exit_date="2026-05-10",
        notes="test",
    )


def test_long_and_short_outcome_math():
    # Long scenario: buy 100, close 110 = +10% before fees.
    long_pred = _build_prediction("L1", "LONG")
    long_out = spec.compute_outcome(
        long_pred,
        close_date=date(2026, 4, 20),
        close_price_aud=110.0,
        include_tax=False,
    )
    assert long_out.shares == 10
    assert long_out.actual_return_pct == pytest.approx(10.0, rel=1e-6)
    assert long_out.gross_gain_aud == pytest.approx(100.0, rel=1e-6)
    assert long_out.fees_aud == pytest.approx(6.0, rel=1e-6)
    assert long_out.net_after_tax_aud == pytest.approx(94.0, rel=1e-6)
    assert long_out.direction_correct is True

    # Short scenario: short 100, close 90 = +10% before fees.
    short_pred = _build_prediction("S1", "SHORT")
    short_out = spec.compute_outcome(
        short_pred,
        close_date=date(2026, 4, 20),
        close_price_aud=90.0,
        include_tax=False,
    )
    assert short_out.shares == 10
    assert short_out.actual_return_pct == pytest.approx(10.0, rel=1e-6)
    assert short_out.gross_gain_aud == pytest.approx(100.0, rel=1e-6)
    assert short_out.net_after_tax_aud == pytest.approx(94.0, rel=1e-6)
    assert short_out.direction_correct is True


def test_register_roundtrip_and_summary(tmp_path):
    path = tmp_path / "speculation_register.csv"

    first = _build_prediction("R1", "LONG")
    spec.add_prediction(first, path=path)

    loaded = spec.load_register(path)
    assert len(loaded) == 1
    assert loaded[0].prediction_id == "R1"
    assert loaded[0].is_open

    closed, outcome = spec.close_prediction("R1", date(2026, 4, 20), 110.0, path=path)
    assert closed.status == "closed"
    assert outcome.actual_return_pct == pytest.approx(10.0, rel=1e-6)

    loaded_after = spec.load_register(path)
    assert loaded_after[0].status == "closed"
    assert not loaded_after[0].is_open

    summary = spec.summarise(loaded_after)
    assert summary.total_predictions == 1
    assert summary.closed_count == 1
    assert summary.open_count == 0
    assert summary.hit_rate_pct == 100.0


def test_next_id_is_unique():
    ids = {spec.next_prediction_id() for _ in range(10)}
    assert len(ids) == 10
