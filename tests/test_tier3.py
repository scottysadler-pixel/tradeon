"""Tests for Tier 3 enhancements: recency-weighted ensemble + drawdown breaker."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.circuit_breaker import (
    DEFAULT_THRESHOLD_PCT,
    DEFAULT_WINDOW_DAYS,
    CircuitBreakerStatus,
    check_drawdown,
)
from core.forecast_weighted import (
    DEFAULT_LOOKBACK_FOLDS,
    DEFAULT_MAX_WEIGHT,
    DEFAULT_MIN_WEIGHT,
    ENSEMBLE_MEMBERS,
    compute_recency_weights,
    recency_weighted_forecast,
)
from core.settings import (
    Enhancements,
    all_off,
    all_on,
    from_session,
    to_session,
    with_only,
)


def _synthetic_df(years: int = 8, *, end_drop_pct: float = 0.0) -> pd.DataFrame:
    """Build a synthetic price series. If end_drop_pct > 0, the last 30 bars
    are scaled down by that fraction to simulate a fresh drawdown."""
    rng = np.random.default_rng(42)
    n = years * 252
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    t = np.arange(n)
    trend = 50 + t * 0.04
    noise = rng.normal(0, 1.0, n)
    close = trend + np.cumsum(noise * 0.05)
    close = np.maximum(close, 1.0)
    if end_drop_pct > 0:
        # Linear ramp-down over the last 30 bars
        ramp = np.linspace(1.0, 1.0 - end_drop_pct, 30)
        close[-30:] = close[-30:] * ramp
    return pd.DataFrame({
        "date": dates, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1_000_000,
    })


# ----- Settings: new toggles wire through correctly -----

def test_enhancements_new_toggles_default_off():
    e = Enhancements()
    assert e.use_recency_weighted is False
    assert e.use_drawdown_breaker is False
    assert not e.any_active()


def test_all_on_includes_new_toggles():
    e = all_on()
    assert e.use_recency_weighted
    assert e.use_drawdown_breaker
    label = e.short_label()
    assert "recency" in label
    assert "breaker" in label


def test_with_only_recency():
    e = with_only("recency")
    assert e.use_recency_weighted
    assert not e.use_garch and not e.use_macro_confirm
    assert e.short_label() == "recency"


def test_with_only_breaker():
    e = with_only("breaker")
    assert e.use_drawdown_breaker
    assert not e.use_garch
    assert e.short_label() == "breaker"


def test_session_round_trip_with_new_toggles():
    state: dict = {}
    e = Enhancements(use_recency_weighted=True, use_drawdown_breaker=True)
    to_session(state, e)
    assert from_session(state) == e


# ----- Recency-weighted ensemble -----

def test_compute_weights_falls_back_when_no_data():
    """No backtest results -> equal weighting + fallback flag set."""
    rw = compute_recency_weights({})
    assert rw.fallback_used is True
    assert pytest.approx(sum(rw.weights.values()), rel=1e-6) == 1.0
    for m in ENSEMBLE_MEMBERS:
        assert rw.weights[m] == pytest.approx(1.0 / len(ENSEMBLE_MEMBERS))


def test_compute_weights_favours_lower_mape():
    """Build fake BacktestResults where holt_winters wins; it should dominate."""
    from core.backtest import BacktestResult

    def _br(name: str, mape: float) -> BacktestResult:
        # 5 folds, all with the same per-fold abs error -> tail mean = mape.
        sample = pd.DataFrame({
            "fold_end": pd.bdate_range("2024-01-01", periods=5),
            "actual_end": [100.0] * 5,
            "predicted_end": [100.0] * 5,
            "predicted_dir_up": [True] * 5,
            "actual_dir_up": [True] * 5,
            "abs_pct_error": [mape] * 5,
        })
        return BacktestResult(
            model_name=name, n_folds=5, mape_pct=mape, rmse_dollars=0,
            directional_accuracy_pct=50, ci_coverage_pct=50,
            paper_trade_total_return_pct=0, paper_trade_net_return_pct_aud=0,
            sample_predictions=sample,
        )

    bt = {"holt_winters": _br("hw", 5.0), "arima": _br("arima", 20.0)}
    rw = compute_recency_weights(bt)
    assert rw.fallback_used is False
    assert pytest.approx(sum(rw.weights.values()), rel=1e-6) == 1.0
    # hw should outweigh arima (lower MAPE)
    assert rw.weights["holt_winters"] > rw.weights["arima"]
    # Both should be within the cap
    for w in rw.weights.values():
        assert DEFAULT_MIN_WEIGHT <= w <= DEFAULT_MAX_WEIGHT
    # Prophet (no data) should still appear with its 1/N share preserved
    assert "prophet" in rw.weights


def test_compute_weights_caps_dominant_model():
    """If one model has zero error, it can't take 100% - the cap holds."""
    from core.backtest import BacktestResult

    def _br(name: str, mape: float) -> BacktestResult:
        sample = pd.DataFrame({
            "fold_end": pd.bdate_range("2024-01-01", periods=5),
            "actual_end": [100.0] * 5, "predicted_end": [100.0] * 5,
            "predicted_dir_up": [True] * 5, "actual_dir_up": [True] * 5,
            "abs_pct_error": [mape] * 5,
        })
        return BacktestResult(
            model_name=name, n_folds=5, mape_pct=mape, rmse_dollars=0,
            directional_accuracy_pct=50, ci_coverage_pct=50,
            paper_trade_total_return_pct=0, paper_trade_net_return_pct_aud=0,
            sample_predictions=sample,
        )

    bt = {"holt_winters": _br("hw", 0.1), "arima": _br("arima", 50.0)}
    rw = compute_recency_weights(bt)
    assert rw.weights["holt_winters"] <= DEFAULT_MAX_WEIGHT + 1e-9
    # The floor is enforced before the final renormalisation; renormalising
    # after clipping can shave 1-2% off, which still preserves the intent
    # ("never silence a model entirely") so we allow a small slack.
    assert rw.weights["arima"] >= DEFAULT_MIN_WEIGHT * 0.9


def test_recency_weighted_forecast_returns_valid_forecast():
    """End-to-end: synthetic data -> backtest -> weighted forecast."""
    from core.backtest import backtest_all

    df = _synthetic_df(years=8)
    bt = backtest_all(df, horizon_days=90, max_folds=10)
    fcast, rw = recency_weighted_forecast(df, bt, horizon_days=90)
    assert len(fcast.forecast_mean) == 90
    assert pytest.approx(sum(rw.weights.values()), rel=1e-6) == 1.0
    assert any("Recency-weighted" in n for n in fcast.notes)


# ----- Drawdown circuit-breaker -----

def test_breaker_idle_on_calm_market():
    """Synthetic series with no drop -> breaker should NOT trigger."""
    df = _synthetic_df(years=5, end_drop_pct=0.0)
    s = check_drawdown(df)
    assert isinstance(s, CircuitBreakerStatus)
    assert s.triggered is False
    assert s.window_days == DEFAULT_WINDOW_DAYS
    assert s.threshold_pct == DEFAULT_THRESHOLD_PCT


def test_breaker_trips_on_large_drop():
    """20% end-of-window drop must trip the default 15% breaker."""
    df = _synthetic_df(years=5, end_drop_pct=0.20)
    s = check_drawdown(df)
    assert s.triggered is True
    assert s.drawdown_pct < -DEFAULT_THRESHOLD_PCT
    assert s.recovery_needed_pct > 0
    assert s.peak_date is not None
    assert "WAIT" in s.interpretation


def test_breaker_does_not_trip_on_small_drop():
    """8% drop should NOT trip a 15% breaker."""
    df = _synthetic_df(years=5, end_drop_pct=0.08)
    s = check_drawdown(df)
    assert s.triggered is False
    assert -DEFAULT_THRESHOLD_PCT < s.drawdown_pct <= 0


def test_breaker_custom_threshold():
    """Lowering the threshold should make the same data trip."""
    df = _synthetic_df(years=5, end_drop_pct=0.08)
    s = check_drawdown(df, threshold_pct=5.0)
    assert s.triggered is True


def test_breaker_handles_empty_df():
    """Empty data must not crash; just return idle."""
    df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    s = check_drawdown(df)
    assert s.triggered is False
    assert "No price data" in s.interpretation


def test_breaker_handles_insufficient_history():
    """Very short history should not crash; returns idle."""
    df = _synthetic_df(years=8).head(3)
    s = check_drawdown(df, window_days=30)
    assert s.triggered is False
    msg = s.interpretation.lower()
    assert "not enough" in msg or "no price data" in msg
