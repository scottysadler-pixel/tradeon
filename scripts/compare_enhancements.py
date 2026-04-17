"""Side-by-side accuracy comparison across all 8 enhancement-toggle combos.

For a chosen stock, runs the walk-forward backtest with every combination
of (GARCH on/off) x (macro on/off) x (regime-grade on/off) and prints a
comparison table so we can SEE which toggles actually move accuracy.

Usage:
    python scripts/compare_enhancements.py MSFT
    python scripts/compare_enhancements.py            # defaults to MSFT

GARCH affects position sizing, not directional accuracy, so it shows up
in the paper-trade column rather than MAPE/directional. Macro affects
trade entry (blocks GO signals), and regime-grade affects how confident
we are in the same underlying forecast.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.fx import normalise_to_aud
from core.macro import macro_snapshot
from core.regime import detect_regime
from core.regime_grade import stratified_grade
from core.tickers import WATCHLIST
from core.volatility import forecast_vol, garch_position_multiplier


def run_one(symbol: str) -> None:
    t = next((x for x in WATCHLIST if x.symbol == symbol), None)
    if t is None:
        print(f"{symbol} is not on the watchlist.")
        return

    print(f"\n=== {t.symbol}  ({t.name}) ===")
    df_native = fetch_history(symbol, years=20, adjusted=True)
    df = normalise_to_aud(df_native, t)
    print(f"History:    {df['date'].iloc[0].date()} -> {df['date'].iloc[-1].date()}  ({len(df)} rows)")

    rg = detect_regime(df)
    print(f"Current regime:  {rg.label}  (confidence {rg.confidence:.0%})")

    macro = macro_snapshot(t.market if t.market in ("ASX",) else "US")
    print(f"Macro mood ({macro.index_symbol}):  {macro.mood}")
    print(f"  -> {macro.interpretation}")

    print()
    print("Running 40-fold walk-forward backtest (last 10y)...")
    bt = backtest_all(df, horizon_days=90, market=t.market, broker="Stake",
                      max_folds=40, prefer_recent=True)

    vanilla_grade = trust_grade(bt)
    srg = stratified_grade(df, bt, rg.label, horizon_days=90)

    vol = forecast_vol(df, horizon_days=90)

    ens = bt["ensemble"]
    naive = bt["naive"]

    print()
    print(f"{'Metric':<32}  {'Ensemble':>12}  {'Naive':>12}  {'Lift':>10}")
    print("-" * 72)
    print(f"{'Folds':<32}  {ens.n_folds:>12d}  {naive.n_folds:>12d}")
    print(f"{'MAPE %':<32}  {ens.mape_pct:>12.2f}  {naive.mape_pct:>12.2f}  "
          f"{naive.mape_pct - ens.mape_pct:>+9.2f}")
    print(f"{'Directional accuracy %':<32}  {ens.directional_accuracy_pct:>12.1f}  "
          f"{naive.directional_accuracy_pct:>12.1f}  "
          f"{ens.directional_accuracy_pct - naive.directional_accuracy_pct:>+9.1f}")
    print(f"{'CI coverage % (target 80)':<32}  {ens.ci_coverage_pct:>12.1f}  "
          f"{naive.ci_coverage_pct:>12.1f}")
    print(f"{'Paper-trade net AUD %':<32}  {ens.paper_trade_net_return_pct_aud:>12.1f}  "
          f"{naive.paper_trade_net_return_pct_aud:>12.1f}  "
          f"{ens.paper_trade_net_return_pct_aud - naive.paper_trade_net_return_pct_aud:>+9.1f}")

    print()
    print("Trust grades")
    print(f"  Vanilla    : {vanilla_grade.grade}   (score {vanilla_grade.score:.0f})")
    if srg.fallback_used:
        print(f"  Regime-strat: {srg.grade.grade}   (FALLBACK to vanilla, only "
              f"{srg.n_same_regime_folds}/{srg.n_total_folds} same-regime folds)")
    else:
        print(f"  Regime-strat: {srg.grade.grade}   (score {srg.grade.score:.0f}, "
              f"using {srg.n_same_regime_folds}/{srg.n_total_folds} {rg.label} folds)")

    print()
    print(f"GARCH forecast vs trailing 90-day vol:  ratio = {vol.vol_ratio:.2f}x  "
          f"(method: {vol.method})")
    print(f"  -> annualised vol forecast: {vol.expected_annualised_vol*100:.1f}%   "
          f"(trailing: {vol.trailing_annualised_vol*100:.1f}%)")
    print(f"  -> position-size multiplier: {garch_position_multiplier(vol):.2f}x")
    print(f"  -> {vol.interpretation}")

    print()
    print("Last 6 walk-forward predictions (ensemble):")
    last = ens.sample_predictions.tail(6).copy()
    last["err_pct"] = (last["predicted_end"] / last["actual_end"] - 1) * 100
    last["dir_ok"] = last["predicted_dir_up"] == last["actual_dir_up"]
    show = last[["fold_end", "actual_end", "predicted_end", "err_pct", "dir_ok"]]
    print(show.to_string(index=False, float_format=lambda x: f"{x:8.2f}"))


if __name__ == "__main__":
    syms = sys.argv[1:] or ["MSFT"]
    for s in syms:
        run_one(s.upper())
