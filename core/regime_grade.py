"""Regime-stratified trust grade (Enhancement #3).

The vanilla trust grade asks "across all 20 historical fold-quarters, how
much better is the ensemble than naive?". That's honest but it averages
across regimes the model behaves very differently in.

This module asks the more useful question: "looking ONLY at past quarters
that started in the same regime as today, how well did the model do?".

So if we're in a bull regime today, the regime-stratified grade tells us:
  "On the 12 historical bull-regime fold quarters, the ensemble beat naive
   by X%."
- which is a much more relevant honesty test for what's happening now.

When the toggle is OFF (default) we use the vanilla all-history grade.
When ON we use the stratified grade if we have at least 5 same-regime folds,
otherwise fall back to vanilla (with a note explaining why).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .backtest import BacktestResult, TrustGrade, _grade_letter
from .regime import RegimeLabel, historical_regime_labels


@dataclass
class RegimeStratifiedGrade:
    """Trust grade computed using only same-regime folds."""

    current_regime: RegimeLabel
    n_same_regime_folds: int
    n_total_folds: int
    grade: TrustGrade
    fallback_used: bool
    interpretation: str
    per_regime_metrics: dict[str, dict[str, float]]   # for UI display


_MIN_SAME_REGIME_FOLDS = 5


def _label_fold_starts(
    df: pd.DataFrame,
    fold_end_dates: pd.Series,
    horizon_days: int,
) -> list[RegimeLabel]:
    """For each fold (identified by its END date), label the regime at the
    fold's START (i.e. when we would have made the prediction)."""
    labels_df = historical_regime_labels(df)
    if labels_df.empty:
        return ["sideways"] * len(fold_end_dates)

    labels_df = labels_df.copy()
    labels_df["date"] = pd.to_datetime(labels_df["date"])
    labels_df = labels_df.set_index("date").sort_index()

    out: list[RegimeLabel] = []
    end_series = pd.to_datetime(fold_end_dates)
    for end in end_series:
        start = end - pd.Timedelta(days=horizon_days)
        # nearest label at or before fold start
        idx = labels_df.index.searchsorted(start, side="right") - 1
        if idx < 0 or idx >= len(labels_df):
            out.append("sideways")
        else:
            label = labels_df.iloc[idx]["regime"]
            out.append(label if label in ("bull", "bear") else "sideways")
    return out


def _summarise_subset(
    ens: BacktestResult,
    naive: BacktestResult,
    mask: np.ndarray,
) -> dict[str, float]:
    """Compute the same trust-grade components on a subset of folds."""
    ens_sp = ens.sample_predictions
    naive_sp = naive.sample_predictions
    if ens_sp.empty or naive_sp.empty or mask.sum() == 0:
        return {"n": 0, "directional_pct": 0, "mape_pct": 0,
                "naive_directional_pct": 0, "naive_mape_pct": 0}

    e = ens_sp[mask].reset_index(drop=True)
    # Build naive subset by matching fold_end dates (naive runs the same folds
    # so they should align positionally - guard against length mismatch).
    if len(naive_sp) == len(ens_sp):
        ns = naive_sp[mask].reset_index(drop=True)
    else:
        # fallback: align on fold_end
        common = pd.merge(e[["fold_end"]], naive_sp, on="fold_end", how="left")
        ns = common.dropna(subset=["actual_end"]).reset_index(drop=True)

    e_dir = float(e["predicted_dir_up"].eq(e["actual_dir_up"]).mean()) * 100
    n_dir = float(ns["predicted_dir_up"].eq(ns["actual_dir_up"]).mean()) * 100 if len(ns) else 0
    e_mape = float(e["abs_pct_error"].mean())
    n_mape = float(ns["abs_pct_error"].mean()) if len(ns) else 0

    return {
        "n": int(len(e)),
        "directional_pct": e_dir,
        "naive_directional_pct": n_dir,
        "mape_pct": e_mape,
        "naive_mape_pct": n_mape,
    }


def stratified_grade(
    df: pd.DataFrame,
    results: dict[str, BacktestResult],
    current_regime: RegimeLabel,
    *,
    horizon_days: int = 90,
) -> RegimeStratifiedGrade:
    """Compute the regime-stratified trust grade for the current regime."""
    ens = results.get("ensemble")
    naive = results.get("naive")
    if not ens or not naive or ens.n_folds == 0:
        return RegimeStratifiedGrade(
            current_regime=current_regime,
            n_same_regime_folds=0,
            n_total_folds=0,
            grade=TrustGrade("F", 0.0, {}, "Insufficient backtest data."),
            fallback_used=True,
            interpretation="No backtest folds available - using vanilla F.",
            per_regime_metrics={},
        )

    sp = ens.sample_predictions
    fold_regimes = _label_fold_starts(df, sp["fold_end"], horizon_days)
    fr_arr = np.array(fold_regimes)

    per_regime: dict[str, dict[str, float]] = {}
    for r in ("bull", "bear", "sideways"):
        per_regime[r] = _summarise_subset(ens, naive, fr_arr == r)

    same = per_regime.get(current_regime, {"n": 0})
    if same["n"] < _MIN_SAME_REGIME_FOLDS:
        # Fall back to all-history grade to avoid spurious A/F from tiny samples
        from .backtest import trust_grade as _vanilla_grade
        fallback = _vanilla_grade(results)
        interp = (
            f"Only {same['n']} historical {current_regime} folds available "
            f"(< {_MIN_SAME_REGIME_FOLDS} minimum) - falling back to all-history "
            f"grade {fallback.grade}."
        )
        return RegimeStratifiedGrade(
            current_regime=current_regime,
            n_same_regime_folds=same["n"],
            n_total_folds=len(sp),
            grade=fallback,
            fallback_used=True,
            interpretation=interp,
            per_regime_metrics=per_regime,
        )

    # Compute grade from the subset metrics, using the same component formula
    # as core.backtest.trust_grade but on subset numbers.
    e_dir = same["directional_pct"]
    n_dir = same["naive_directional_pct"]
    e_mape = same["mape_pct"]
    n_mape = same["naive_mape_pct"]

    directional_lift = 50 + min(50, max(-50, (e_dir - n_dir) * 2))
    if n_mape > 0:
        mape_ratio = e_mape / n_mape
        mape_lift = 50 + min(50, max(-50, (1 - mape_ratio) * 100))
    else:
        mape_lift = 50
    # CI quality + net-return lift unavailable on subset; use vanilla values
    from .backtest import trust_grade as _vanilla_grade
    vanilla = _vanilla_grade(results)
    ci_quality = vanilla.components.get("ci_coverage_quality", 50.0)
    net_lift = vanilla.components.get("net_return_lift_vs_baseline", 50.0)

    score = (
        0.35 * directional_lift
        + 0.25 * mape_lift
        + 0.10 * ci_quality
        + 0.30 * net_lift
    )
    letter = _grade_letter(score)
    components = {
        "directional_lift_vs_baseline": directional_lift,
        "mape_lift_vs_baseline": mape_lift,
        "ci_coverage_quality": ci_quality,
        "net_return_lift_vs_baseline": net_lift,
    }
    interp = (
        f"Regime-stratified grade {letter} - based on {same['n']} historical "
        f"{current_regime}-regime quarters. Ensemble {e_dir:.0f}% directional vs "
        f"naive {n_dir:.0f}%; MAPE {e_mape:.1f}% vs naive {n_mape:.1f}%."
    )
    return RegimeStratifiedGrade(
        current_regime=current_regime,
        n_same_regime_folds=int(same["n"]),
        n_total_folds=int(len(sp)),
        grade=TrustGrade(letter, float(score), components, interp),
        fallback_used=False,
        interpretation=interp,
        per_regime_metrics=per_regime,
    )
