"""Stage-by-stage profile of one analyse_one() call.

Run: python scripts/profile_stages.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.earnings_proxy import detect as earnings_detect
from core.forecast import ensemble_forecast, naive_forecast
from core.fx import normalise_to_aud
from core.hold_window import upcoming_window
from core.regime import detect_regime
from core.signals import decide
from core.stops import suggest as stops_suggest
from core.technicals import snapshot as tech_snapshot
from core.tickers import WATCHLIST


def stage(label: str, fn, *args, **kwargs):
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    print(f"  {label:<32} {elapsed:6.2f}s")
    return res, elapsed


def main() -> None:
    symbol = "MSFT"
    print(f"Stage profile for analyse_one('{symbol}'):")
    print("=" * 56)

    t = next(x for x in WATCHLIST if x.symbol == symbol)
    timings: dict[str, float] = {}

    df_native, t_fetch = stage("fetch_history", fetch_history, symbol, years=20, adjusted=True)
    timings["fetch_history"] = t_fetch

    df, t_fx = stage("normalise_to_aud", normalise_to_aud, df_native, t)
    timings["normalise_to_aud"] = t_fx

    bt, t_bt = stage("backtest_all (20 folds)", backtest_all, df, horizon_days=90,
                     market=t.market, broker="Stake", max_folds=20)
    timings["backtest_all"] = t_bt

    rg, t_reg = stage("detect_regime", detect_regime, df)
    timings["detect_regime"] = t_reg

    grade, t_tg = stage("trust_grade", trust_grade, bt)
    timings["trust_grade"] = t_tg

    fcast, t_ens = stage("ensemble_forecast", ensemble_forecast, df, horizon_days=90)
    timings["ensemble_forecast"] = t_ens

    naive, t_nv = stage("naive_forecast", naive_forecast, df, horizon_days=90)
    timings["naive_forecast"] = t_nv

    snap, t_sn = stage("tech_snapshot", tech_snapshot, df)
    timings["tech_snapshot"] = t_sn

    earn, t_er = stage("earnings_detect", earnings_detect, df)
    timings["earnings_detect"] = t_er

    spot = float(df["close"].iloc[-1])
    stops, t_st = stage("stops_suggest", stops_suggest, df, hold_days=90, current_price=spot)
    timings["stops_suggest"] = t_st

    hold, t_hw = stage(
        "upcoming_window", upcoming_window, df, current_month=datetime.today().month
    )
    timings["upcoming_window"] = t_hw

    naive_drift = ((float(naive.forecast_mean[-1]) / spot) - 1) * 100
    sig, t_dec = stage("decide", decide, trust=grade, regime=rg, hold=hold, forecast=fcast,
                       technicals=snap, earnings=earn, stops=stops,
                       spot_price=spot, naive_baseline_drift_pct=naive_drift)
    timings["decide"] = t_dec

    total = sum(timings.values())
    print("-" * 56)
    print(f"  TOTAL                            {total:6.2f}s")
    print()
    print("Largest contributors:")
    for k, v in sorted(timings.items(), key=lambda kv: -kv[1])[:5]:
        pct = 100 * v / total
        print(f"  {k:<32} {v:6.2f}s  ({pct:.1f}%)")


if __name__ == "__main__":
    main()
