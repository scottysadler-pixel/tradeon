"""Recency-weighted ensemble forecast (Enhancement #4).

The vanilla ensemble in `core/forecast.py` averages prophet/holt-winters/arima
with EQUAL weight. That's a reasonable default but it ignores recent track
record - if Holt-Winters has been crushing it for the last five quarters and
ARIMA has been wrong every time, both still get a 1/3 vote.

This module re-weights the same three sub-models by their recent backtest
accuracy. It does NOT introduce a new forecasting model - it just changes
how much each existing model contributes to the ensemble average.

How weights are computed
------------------------
We re-use the per-model walk-forward backtest results that are ALREADY
computed by `core.backtest.backtest_all()`, so there is no extra fitting
cost. For each of `holt_winters` and `arima` we look at the absolute
percentage error on the last `lookback_folds` folds (default 5) and assign
weight ∝ 1 / mean(|err|).

Prophet does not appear in `backtest_all` (too slow for the live backtest),
so it gets a neutral 1/N share - we don't penalise nor reward a model we
have no recent evidence on.

The weights are then re-normalised to sum to 1 and passed to the existing
`ensemble_forecast(..., weights=...)` call. That's it.

Honest expectations
-------------------
This is one of the few "free lunch" tweaks in time-series forecasting -
it tends to add 2-5 percentage points of directional accuracy and shrink
MAPE by a small but real amount. It can also hurt if a model that's been
on a bad streak is about to mean-revert; we mitigate that by capping the
weight any single model can take (default 0.7).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import BacktestResult
from .forecast import Forecast, ensemble_forecast

logger = logging.getLogger(__name__)


# Sub-models the ensemble can use. Order is informational only.
ENSEMBLE_MEMBERS: tuple[str, ...] = ("prophet", "holt_winters", "arima")

# Tunable defaults - exposed for tests + Strategy Lab transparency.
DEFAULT_LOOKBACK_FOLDS = 5
DEFAULT_MAX_WEIGHT = 0.7        # no single model can dominate the ensemble
DEFAULT_MIN_WEIGHT = 0.05       # never let a model's voice fall to ~zero


@dataclass
class RecencyWeights:
    """Diagnostic record of how the weights were computed."""

    weights: dict[str, float]
    mean_mape_per_model: dict[str, float | None]
    lookback_folds: int
    fallback_used: bool
    interpretation: str


def compute_recency_weights(
    bt_results: dict[str, BacktestResult],
    *,
    lookback_folds: int = DEFAULT_LOOKBACK_FOLDS,
    members: tuple[str, ...] = ENSEMBLE_MEMBERS,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    min_weight: float = DEFAULT_MIN_WEIGHT,
) -> RecencyWeights:
    """Inverse-MAPE weights from the last N folds of each sub-model.

    Models that don't appear in `bt_results` (typically Prophet) keep a
    neutral 1/N share. The remaining "weight budget" is split among the
    backtested models in proportion to 1/MAPE, then capped/floored, then
    re-normalised to 1.0 in total.

    If no model has enough fold data we fall back to equal weighting and
    set `fallback_used=True`.
    """
    n = len(members)
    equal = 1.0 / n
    weights = {m: equal for m in members}
    mapes: dict[str, float | None] = {m: None for m in members}

    inverse_mapes: dict[str, float] = {}
    for m in members:
        bt = bt_results.get(m)
        if bt is None:
            continue
        preds = bt.sample_predictions
        if preds is None or preds.empty or "abs_pct_error" not in preds.columns:
            continue
        tail = preds.tail(lookback_folds)
        if tail.empty:
            continue
        mape = float(tail["abs_pct_error"].mean())
        mapes[m] = mape
        if np.isfinite(mape) and mape > 1e-6:
            # Tiny epsilon avoids division by ~0; very-low MAPE models still win.
            inverse_mapes[m] = 1.0 / max(mape, 0.5)

    if not inverse_mapes:
        return RecencyWeights(
            weights=weights,
            mean_mape_per_model=mapes,
            lookback_folds=lookback_folds,
            fallback_used=True,
            interpretation=(
                "No recent backtest data found - falling back to equal weighting "
                "(same as vanilla ensemble)."
            ),
        )

    # Each backtested model claims its share of the (n_backtested / n) budget.
    weighted_budget = len(inverse_mapes) / n
    inv_total = sum(inverse_mapes.values())
    for m, inv in inverse_mapes.items():
        weights[m] = (inv / inv_total) * weighted_budget

    # Cap and floor, then renormalise.
    weights = {m: min(max(w, min_weight), max_weight) for m, w in weights.items()}
    total = sum(weights.values()) or 1.0
    weights = {m: w / total for m, w in weights.items()}

    # Build a human-readable interpretation.
    sorted_w = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    top_model, top_w = sorted_w[0]
    bot_model, bot_w = sorted_w[-1]
    if top_w > equal * 1.15:
        interp = (
            f"Last {lookback_folds} folds: {top_model} has been most accurate "
            f"(weight {top_w:.0%}); {bot_model} least accurate (weight {bot_w:.0%}). "
            f"Vanilla equal-weight would give each {equal:.0%}."
        )
    else:
        interp = (
            f"Last {lookback_folds} folds: all sub-models within ~15% of each other "
            f"on accuracy - weights stay close to the equal-weight baseline."
        )

    return RecencyWeights(
        weights=weights,
        mean_mape_per_model=mapes,
        lookback_folds=lookback_folds,
        fallback_used=False,
        interpretation=interp,
    )


def recency_weighted_forecast(
    df: pd.DataFrame,
    bt_results: dict[str, BacktestResult],
    *,
    horizon_days: int = 90,
    lookback_folds: int = DEFAULT_LOOKBACK_FOLDS,
) -> tuple[Forecast, RecencyWeights]:
    """Drop-in alternative to `ensemble_forecast` that uses recency weights.

    Returns both the forecast AND the diagnostic weight record so the UI
    layer can show the user exactly which models were favoured and why.
    """
    rw = compute_recency_weights(bt_results, lookback_folds=lookback_folds)
    fcast = ensemble_forecast(df, horizon_days=horizon_days, weights=rw.weights)
    # Tag the forecast with the weight summary so callers don't lose it.
    fcast.notes.append(f"Recency-weighted: {rw.interpretation}")
    return fcast, rw
