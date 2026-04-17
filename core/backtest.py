"""Walk-forward backtesting and trust-grade computation.

This is the honesty engine. We replay history: pick a date, pretend
that's 'today', generate a forecast, slide forward the horizon, compare
forecast to what really happened. Repeat across years.

Every metric is reported BOTH absolutely AND relative to the naive
random-walk baseline. If our ensemble doesn't beat 'tomorrow = today',
we say so loudly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import net_trade_outcome
from .forecast import (
    arima_forecast,
    ensemble_forecast,
    holt_winters_forecast,
    naive_forecast,
    seasonal_naive_forecast,
)


@dataclass
class BacktestResult:
    model_name: str
    n_folds: int
    mape_pct: float
    rmse_dollars: float
    directional_accuracy_pct: float
    ci_coverage_pct: float
    paper_trade_total_return_pct: float       # gross
    paper_trade_net_return_pct_aud: float     # after fees & tax in AUD
    sample_predictions: pd.DataFrame


@dataclass
class TrustGrade:
    grade: str                  # 'A' .. 'F'
    score: float                # 0..100
    components: dict[str, float]
    interpretation: str


def _walk_forward_folds(
    df: pd.DataFrame,
    *,
    train_min_days: int = 252 * 5,
    horizon_days: int = 90,
    step_days: int = 90,
    max_folds: int = 20,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Generate (train, test) splits walking forward through history."""
    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    n = len(df)
    if n < train_min_days + horizon_days:
        return folds
    start = train_min_days
    while start + horizon_days <= n:
        train = df.iloc[:start].reset_index(drop=True)
        test = df.iloc[start : start + horizon_days].reset_index(drop=True)
        folds.append((train, test))
        start += step_days
        if len(folds) >= max_folds:
            break
    # Keep most recent (most representative) folds if we capped
    return folds


def backtest_model(
    df: pd.DataFrame,
    model_fn,
    *,
    horizon_days: int = 90,
    market: str = "ASX",
    broker: str = "Stake",
    capital_aud: float = 1000.0,
) -> BacktestResult:
    """Run walk-forward backtest of a single forecasting model."""
    folds = _walk_forward_folds(df, horizon_days=horizon_days)
    if not folds:
        return BacktestResult("(insufficient data)", 0, 0, 0, 0, 0, 0, 0, pd.DataFrame())

    abs_pct_errors: list[float] = []
    sq_errors: list[float] = []
    direction_score = 0.0  # accumulates 1.0 per hit, 0.5 per "no call", 0 per miss
    in_band_count = 0
    paper_trade_returns: list[float] = []
    net_returns_aud: list[float] = []
    sample_rows: list[dict] = []
    model_name = "?"

    # A "no call" is any predicted move smaller than 0.5% of starting price -
    # essentially the model abstaining from picking a direction.
    NO_CALL_THRESHOLD_PCT = 0.5

    for train, test in folds:
        try:
            f = model_fn(train, horizon_days)
        except Exception:
            continue
        model_name = f.model_name

        actual_end = float(test["close"].iloc[-1])
        actual_start = float(train["close"].iloc[-1])
        predicted_end = float(f.forecast_mean[-1])

        abs_pct_errors.append(abs((predicted_end - actual_end) / actual_end) * 100)
        sq_errors.append((predicted_end - actual_end) ** 2)

        predicted_dir = predicted_end - actual_start
        actual_dir = actual_end - actual_start
        predicted_pct = abs(predicted_dir / actual_start) * 100 if actual_start else 0
        if predicted_pct < NO_CALL_THRESHOLD_PCT:
            # Model essentially declined to pick a direction - score as coin flip
            direction_score += 0.5
        elif np.sign(predicted_dir) == np.sign(actual_dir):
            direction_score += 1.0

        if f.forecast_lower[-1] <= actual_end <= f.forecast_upper[-1]:
            in_band_count += 1

        # Paper trade: if model predicts up, "buy" at end of train, "sell" at end of test
        if predicted_dir > 0:
            shares = int(capital_aud // actual_start) if actual_start > 0 else 0
            if shares > 0:
                gross_ret = (actual_end / actual_start) - 1
                paper_trade_returns.append(gross_ret * 100)
                trade = net_trade_outcome(
                    buy_price_aud=actual_start,
                    sell_price_aud=actual_end,
                    shares=shares,
                    held_days=horizon_days,
                    market=market,
                    broker=broker,
                )
                net_returns_aud.append(trade["net_return_pct"])

        sample_rows.append({
            "fold_end": pd.Timestamp(test["date"].iloc[-1]),
            "actual_end": actual_end,
            "predicted_end": predicted_end,
            "predicted_dir_up": bool(predicted_dir > 0),
            "actual_dir_up": bool(actual_dir > 0),
            "abs_pct_error": abs_pct_errors[-1],
        })

    if not abs_pct_errors:
        return BacktestResult(model_name, 0, 0, 0, 0, 0, 0, 0, pd.DataFrame())

    return BacktestResult(
        model_name=model_name,
        n_folds=len(abs_pct_errors),
        mape_pct=float(np.mean(abs_pct_errors)),
        rmse_dollars=float(np.sqrt(np.mean(sq_errors))),
        directional_accuracy_pct=(direction_score / len(abs_pct_errors)) * 100,
        ci_coverage_pct=(in_band_count / len(abs_pct_errors)) * 100,
        paper_trade_total_return_pct=float(np.sum(paper_trade_returns)) if paper_trade_returns else 0.0,
        paper_trade_net_return_pct_aud=float(np.sum(net_returns_aud)) if net_returns_aud else 0.0,
        sample_predictions=pd.DataFrame(sample_rows),
    )


def backtest_all(
    df: pd.DataFrame,
    *,
    horizon_days: int = 90,
    market: str = "ASX",
    broker: str = "Stake",
) -> dict[str, BacktestResult]:
    """Run all models and return a dict of results keyed by model name."""
    return {
        "naive":        backtest_model(df, naive_forecast, horizon_days=horizon_days, market=market, broker=broker),
        "seasonal":     backtest_model(df, seasonal_naive_forecast, horizon_days=horizon_days, market=market, broker=broker),
        "holt_winters": backtest_model(df, holt_winters_forecast, horizon_days=horizon_days, market=market, broker=broker),
        "arima":        backtest_model(df, arima_forecast, horizon_days=horizon_days, market=market, broker=broker),
        "ensemble":     backtest_model(df, ensemble_forecast, horizon_days=horizon_days, market=market, broker=broker),
    }


# ----- Trust grade computation ------------------------------------------

def _grade_letter(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def trust_grade(results: dict[str, BacktestResult]) -> TrustGrade:
    """Composite trust grade from ensemble vs naive baseline.

    Components (each scored 0-100):
      - directional_lift  : how much better ensemble is at calling direction vs naive
      - mape_lift         : how much smaller ensemble's MAPE is vs naive
      - ci_quality        : how close 80% CI coverage is to nominal 80%
      - net_return_lift   : how much better paper-trade net AUD return is vs naive
    """
    ens = results.get("ensemble")
    naive = results.get("naive")
    if not ens or not naive or ens.n_folds == 0:
        return TrustGrade(
            grade="F",
            score=0.0,
            components={},
            interpretation="Insufficient backtest data to grade this stock.",
        )

    # 1. Directional lift (50 = baseline; 100 = +25 percentage points or better)
    directional_lift = 50 + min(50, max(-50, (ens.directional_accuracy_pct - naive.directional_accuracy_pct) * 2))

    # 2. MAPE lift (50 = same as naive; 100 = 50% better; 0 = 50% worse)
    if naive.mape_pct > 0:
        mape_ratio = ens.mape_pct / naive.mape_pct
        mape_lift = 50 + min(50, max(-50, (1 - mape_ratio) * 100))
    else:
        mape_lift = 50

    # 3. CI quality (100 if exactly 80%, dropping linearly)
    ci_quality = 100 - min(100, abs(ens.ci_coverage_pct - 80) * 2)

    # 4. Net return lift (capped)
    net_lift = 50 + min(50, max(-50, ens.paper_trade_net_return_pct_aud - naive.paper_trade_net_return_pct_aud))

    components = {
        "directional_lift_vs_baseline": directional_lift,
        "mape_lift_vs_baseline": mape_lift,
        "ci_coverage_quality": ci_quality,
        "net_return_lift_vs_baseline": net_lift,
    }
    score = (
        0.35 * directional_lift
        + 0.25 * mape_lift
        + 0.10 * ci_quality
        + 0.30 * net_lift
    )
    grade = _grade_letter(score)

    if grade in ("A", "B"):
        interp = (
            f"Grade {grade}. The ensemble has been meaningfully better than the "
            f"naive baseline across {ens.n_folds} historical quarters - this "
            "stock's predictions can be taken seriously."
        )
    elif grade == "C":
        interp = (
            f"Grade {grade}. Ensemble is roughly tied with the naive baseline. "
            "Treat this stock's predictions with caution."
        )
    else:
        interp = (
            f"Grade {grade}. Ensemble has NOT consistently beaten the naive "
            "baseline. Ignore predictions on this stock - the model isn't "
            "earning its keep here."
        )

    return TrustGrade(grade=grade, score=score, components=components, interpretation=interp)


def model_weights_from_backtest(results: dict[str, BacktestResult]) -> dict[str, float]:
    """Inverse-MAPE weighting for the ensemble: more accurate models get more weight."""
    out: dict[str, float] = {}
    for k in ("prophet", "holt_winters", "arima"):
        r = results.get(k)
        if r and r.mape_pct > 0:
            out[k] = 1.0 / r.mape_pct
    if not out:
        return {}
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}
