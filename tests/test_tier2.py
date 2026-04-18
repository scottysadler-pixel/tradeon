"""Tests for Tier 2 enhancements: settings, volatility, macro, regime-grade."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.settings import (
    Enhancements, all_off, all_on, with_only,
    from_session, to_session,
)
from core.volatility import (
    VolatilityForecast, forecast_vol,
    garch_band_multiplier, garch_position_multiplier,
)


def _synthetic_df(years: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=years * 252)
    n = len(dates)
    t = np.arange(n)
    trend = 50 + t * 0.04
    noise = rng.normal(0, 1.0, n)
    close = trend + np.cumsum(noise * 0.05)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "date": dates, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1_000_000,
    })


# ----- Settings -----

def test_default_enhancements_all_off():
    e = all_off()
    assert e.use_garch is False
    assert e.use_macro_confirm is False
    assert e.use_regime_grade is False
    assert not e.any_active()
    assert e.short_label() == "vanilla"


def test_all_on_active():
    e = all_on()
    assert e.use_garch and e.use_macro_confirm and e.use_regime_grade
    assert e.any_active()
    assert "garch" in e.short_label()


def test_with_only_isolates():
    e = with_only("garch")
    assert e.use_garch
    assert not e.use_macro_confirm
    assert not e.use_regime_grade
    assert e.short_label() == "garch"


def test_session_round_trip():
    """Mimic Streamlit's session_state with a plain dict."""
    state: dict = {}
    assert from_session(state) == all_off()
    e = with_only("macro")
    to_session(state, e)
    assert from_session(state) == e


# ----- Volatility -----

def test_forecast_vol_returns_valid_object():
    df = _synthetic_df()
    vf = forecast_vol(df, horizon_days=90)
    assert isinstance(vf, VolatilityForecast)
    assert vf.horizon_days == 90
    assert vf.expected_period_vol > 0
    assert vf.expected_annualised_vol > 0
    assert vf.trailing_annualised_vol > 0
    assert vf.method in ("garch(1,1)", "rolling-stdev-fallback")


def test_garch_position_multiplier_bounded():
    df = _synthetic_df()
    vf = forecast_vol(df, horizon_days=90)
    m = garch_position_multiplier(vf)
    assert 0.5 <= m <= 1.5


def test_garch_band_multiplier_bounded():
    df = _synthetic_df()
    vf = forecast_vol(df, horizon_days=90)
    m = garch_band_multiplier(vf)
    assert 0.7 <= m <= 1.5


def test_volatility_fallback_on_short_data():
    df = _synthetic_df(years=1)
    vf = forecast_vol(df, horizon_days=90)
    # Should still return a valid object even on too-little data
    assert vf.expected_period_vol > 0


# ----- Regime-stratified grade -----

def test_stratified_grade_falls_back_when_few_folds():
    """With synthetic data and few same-regime folds, must fall back without crashing."""
    from core.backtest import backtest_all
    from core.regime_grade import stratified_grade

    df = _synthetic_df(years=8)
    results = backtest_all(df, horizon_days=90, max_folds=10)
    sg = stratified_grade(df, results, "bull", horizon_days=90)
    assert sg.grade.grade in ("A", "B", "C", "D", "F")
    assert sg.n_total_folds > 0
    # Either uses subset OR falls back gracefully
    assert sg.fallback_used or sg.n_same_regime_folds >= 5


def test_stratified_grade_per_regime_metrics_keys():
    from core.backtest import backtest_all
    from core.regime_grade import stratified_grade

    df = _synthetic_df(years=8)
    results = backtest_all(df, horizon_days=90, max_folds=10)
    sg = stratified_grade(df, results, "sideways", horizon_days=90)
    assert set(sg.per_regime_metrics.keys()) == {"bull", "bear", "sideways"}
    for r in ("bull", "bear", "sideways"):
        assert "n" in sg.per_regime_metrics[r]


# ----- Backtest fold-coverage fix -----

def test_backtest_prefers_recent_folds():
    """With prefer_recent=True, the LAST fold's end-date should be near data end."""
    from core.backtest import _walk_forward_folds

    df = _synthetic_df(years=20)
    folds = _walk_forward_folds(df, horizon_days=90, max_folds=10, prefer_recent=True)
    assert len(folds) <= 10
    last_train, last_test = folds[-1]
    # Last test should end within ~horizon of the data's end
    last_test_date = pd.Timestamp(last_test["date"].iloc[-1])
    data_end_date = pd.Timestamp(df["date"].iloc[-1])
    days_from_end = (data_end_date - last_test_date).days
    assert days_from_end < 100, f"Last fold ends {days_from_end} days before data end"


def test_backtest_old_default_oldest_folds():
    """With prefer_recent=False, the FIRST fold should be near training_min."""
    from core.backtest import _walk_forward_folds

    df = _synthetic_df(years=20)
    folds = _walk_forward_folds(df, horizon_days=90, max_folds=5, prefer_recent=False)
    assert len(folds) == 5
    # First fold's training set should be exactly train_min_days long
    assert len(folds[0][0]) == 252 * 5
