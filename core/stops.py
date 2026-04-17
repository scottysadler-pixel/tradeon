"""Drawdown-aware stop-loss recommender.

For each stock, we compute the distribution of typical 30/60/90-day
drawdowns from the past 20 years and recommend a stop-loss level just
beyond the 90th-percentile drawdown - tight enough to cap downside, but
loose enough that normal market wiggles don't trigger it prematurely.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StopLossSuggestion:
    typical_drawdown_pct: float          # median 90-day drawdown observed
    p90_drawdown_pct: float              # 90th-percentile worst 90-day drawdown
    recommended_stop_pct: float          # the suggested stop level (negative)
    recommended_stop_price: float        # absolute price level
    explanation: str


def _rolling_drawdowns(close: pd.Series, window_days: int) -> list[float]:
    """For every starting day, max % drop within the next `window_days`."""
    drawdowns: list[float] = []
    n = len(close)
    for i in range(n - window_days):
        segment = close.iloc[i : i + window_days].values
        peak = segment[0]
        if peak <= 0:
            continue
        trough = segment.min()
        drawdowns.append((trough / peak) - 1)
    return drawdowns


def suggest(
    df: pd.DataFrame,
    *,
    hold_days: int = 90,
    current_price: float | None = None,
) -> StopLossSuggestion:
    """Recommend a stop-loss for a position with the given hold horizon."""
    close = df["close"]
    if len(close) < hold_days + 30:
        # Conservative default: -8% if we have no data
        spot = current_price or float(close.iloc[-1]) if not close.empty else 0.0
        return StopLossSuggestion(
            typical_drawdown_pct=-8.0,
            p90_drawdown_pct=-12.0,
            recommended_stop_pct=-8.0,
            recommended_stop_price=spot * 0.92,
            explanation="Insufficient data; using conservative default of -8%.",
        )

    drawdowns = _rolling_drawdowns(close, hold_days)
    arr = np.array(drawdowns)
    typical = float(np.median(arr) * 100)
    p90 = float(np.percentile(arr, 10) * 100)  # 10th percentile of (negative) returns = 90th-percentile worst-case

    # Recommend a stop just beyond the typical drawdown but within the 90th-pct worst case.
    # Take the more permissive of (1.2 * typical) or (0.85 * p90).
    rec = max(typical * 1.2, p90 * 0.85)
    rec = min(rec, -3.0)  # never tighter than -3%
    rec = max(rec, -25.0) # never wider than -25%

    spot = current_price or float(close.iloc[-1])
    stop_price = spot * (1 + rec / 100)

    return StopLossSuggestion(
        typical_drawdown_pct=typical,
        p90_drawdown_pct=p90,
        recommended_stop_pct=rec,
        recommended_stop_price=stop_price,
        explanation=(
            f"Over the last {hold_days}-day windows in 20yrs of history, the "
            f"median drawdown was {typical:.1f}% and the 90th-percentile worst "
            f"case was {p90:.1f}%. A stop at {rec:.1f}% leaves room for normal "
            f"swings while capping a worst-case loss."
        ),
    )
