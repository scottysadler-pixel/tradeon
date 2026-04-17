"""End-to-end live test against yfinance.

Run manually with: pytest tests/test_live.py -v -s
Skipped by default if no internet (or yfinance is failing).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from core.analysis import stock_stats
from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.earnings_proxy import detect as earn_detect
from core.forecast import ensemble_forecast, naive_forecast
from core.fx import normalise_to_aud
from core.hold_window import upcoming_window
from core.regime import detect_regime
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snap
from core.tickers import by_symbol


@pytest.mark.parametrize("symbol", ["MSFT", "BHP.AX"])
def test_full_pipeline_live(symbol):
    t = by_symbol(symbol)
    assert t is not None, f"{symbol} not in watchlist"

    print(f"\n=== Pipeline test: {symbol} ===")

    df_raw = fetch_history(symbol, years=20, adjusted=True)
    assert len(df_raw) > 252 * 5, f"Got only {len(df_raw)} rows for {symbol}"
    print(f"  Got {len(df_raw)} rows from {df_raw['date'].min().date()} to {df_raw['date'].max().date()}")

    df = normalise_to_aud(df_raw, t)
    spot = float(df["close"].iloc[-1])
    print(f"  Spot price (AUD): {spot:.2f}")

    s = stock_stats(df)
    print(f"  CAGR={s.cagr_pct:.1f}%  Vol={s.annualised_vol_pct:.1f}%  "
          f"MaxDD={s.max_drawdown_pct:.1f}%  Pattern={s.pattern_strength:.2f}")
    assert -100 < s.max_drawdown_pct <= 0
    assert 0 <= s.pattern_strength <= 1

    bt = backtest_all(df, horizon_days=90, market=t.market, broker="Stake")
    g = trust_grade(bt)
    print(f"  Ensemble: dir={bt['ensemble'].directional_accuracy_pct:.1f}%  "
          f"MAPE={bt['ensemble'].mape_pct:.2f}%")
    print(f"  Naive:    dir={bt['naive'].directional_accuracy_pct:.1f}%  "
          f"MAPE={bt['naive'].mape_pct:.2f}%")
    print(f"  Trust grade: {g.grade} (score {g.score:.0f}/100)")
    print(f"  -> {g.interpretation}")
    assert g.grade in ("A", "B", "C", "D", "F")

    rg = detect_regime(df)
    fc = ensemble_forecast(df, 90)
    nv = naive_forecast(df, 90)
    hold = upcoming_window(df, datetime.today().month)
    sig = decide(
        trust=g, regime=rg, hold=hold, forecast=fc,
        technicals=tech_snap(df), earnings=earn_detect(df),
        stops=stops_suggest(df, hold_days=90, current_price=spot), spot_price=spot,
        naive_baseline_drift_pct=((nv.forecast_mean[-1] / spot) - 1) * 100,
    )
    print(f"  Regime: {rg.label}  Signal: {sig.state}")
    print(f"  -> {sig.headline}")
    assert sig.state in ("GO", "WAIT", "AVOID")
