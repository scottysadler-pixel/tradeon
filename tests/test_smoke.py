"""Lightweight smoke tests for the core engine.

Use synthetic data so we don't depend on the network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core import analysis, costs, forecast, hold_window, regime, signals, technicals


def _synthetic_df(years: int = 6) -> pd.DataFrame:
    """Generate a deterministic price series with trend + seasonality + noise."""
    rng = np.random.default_rng(42)
    # Derive n from the actual date count after bdate_range. pandas >= 3.0
    # can return periods-1 rows depending on whether the end date itself is
    # a business day, so we always trust len(dates) over the requested N.
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=years * 252)
    n = len(dates)
    t = np.arange(n)
    trend = 50 + t * 0.04
    seasonal = 5 * np.sin(2 * np.pi * t / 252)
    noise = rng.normal(0, 1.0, n)
    close = trend + seasonal + np.cumsum(noise * 0.05)
    close = np.maximum(close, 1.0)
    return pd.DataFrame(
        {"date": dates, "open": close, "high": close * 1.01,
         "low": close * 0.99, "close": close, "volume": 1_000_000}
    )


def test_analysis_runs():
    df = _synthetic_df()
    s = analysis.stock_stats(df)
    assert s.cagr_pct > 0
    assert s.annualised_vol_pct > 0
    assert -100 < s.max_drawdown_pct <= 0
    assert 0 <= s.pattern_strength <= 1


def test_quarterly_seasonality_shape():
    df = _synthetic_df()
    qs = analysis.quarterly_seasonality(df)
    assert len(qs) == 4
    assert set(qs.columns) >= {"quarter", "mean_return_pct", "hit_rate_pct"}


def test_hold_window_returns_something():
    df = _synthetic_df(years=10)
    windows = hold_window.best_windows(df, top_n=3)
    assert isinstance(windows, list)


def test_costs_cgt_discount():
    short = costs.cgt_on_gain(1000, held_days=200)
    long = costs.cgt_on_gain(1000, held_days=400)
    assert long < short
    assert long == pytest.approx(short / 2, rel=0.01)


def test_costs_net_trade_outcome():
    out = costs.net_trade_outcome(
        buy_price_aud=10.0, sell_price_aud=11.0, shares=100,
        held_days=90, market="ASX", broker="Stake",
    )
    assert out["gross_gain_aud"] == 100.0
    assert out["fees_aud"] > 0
    assert out["net_gain_aud"] < out["gross_gain_aud"]


def test_naive_forecast_length():
    df = _synthetic_df()
    f = forecast.naive_forecast(df, horizon_days=30)
    assert len(f.forecast_mean) == 30
    assert len(f.forecast_lower) == 30
    assert len(f.forecast_upper) == 30


def test_holt_winters_forecast():
    df = _synthetic_df()
    f = forecast.holt_winters_forecast(df, horizon_days=30)
    assert len(f.forecast_mean) == 30
    assert "Holt-Winters" in f.model_name or "Naive" in f.model_name  # may fall back


def test_arima_forecast():
    df = _synthetic_df()
    f = forecast.arima_forecast(df, horizon_days=30)
    assert len(f.forecast_mean) == 30


def test_ensemble_forecast():
    df = _synthetic_df()
    f = forecast.ensemble_forecast(df, horizon_days=30)
    assert len(f.forecast_mean) == 30
    assert "Ensemble" in f.model_name


def test_technicals_snapshot():
    df = _synthetic_df()
    snap = technicals.snapshot(df)
    assert 0 <= snap.rsi <= 100
    assert isinstance(snap.notes, list) and len(snap.notes) > 0


def test_regime_detection():
    df = _synthetic_df()
    state = regime.detect_regime(df)
    assert state.label in ("bull", "bear", "sideways")


def test_signal_decider_smoke():
    """End-to-end: can we wire all the pieces together without crashing?"""
    df = _synthetic_df()
    from core.backtest import backtest_all, trust_grade
    from core.earnings_proxy import detect as earnings_detect
    from core.stops import suggest as stops_suggest

    results = backtest_all(df, horizon_days=30)
    grade = trust_grade(results)
    state = regime.detect_regime(df)
    f = forecast.ensemble_forecast(df, horizon_days=30)
    snap = technicals.snapshot(df)
    earnings = earnings_detect(df)
    stops_obj = stops_suggest(df, hold_days=30)
    sig = signals.decide(
        trust=grade,
        regime=state,
        hold=None,
        forecast=f,
        technicals=snap,
        earnings=earnings,
        stops=stops_obj,
        spot_price=float(df["close"].iloc[-1]),
    )
    assert sig.state in ("GO", "WAIT", "AVOID")
