"""Drawdown circuit-breaker (Enhancement #5).

A simple, hard safety rule layered on top of the forecasting stack:

    "If a stock has fallen more than X% from its recent peak in the last
     N trading days, force any GO signal down to WAIT regardless of what
     the forecast says."

Why this is needed
------------------
Statistical models trained on price returns systematically misjudge
"falling knife" situations. They see a low price, regress it toward the
trend, and predict mean reversion that may not arrive for months. The
2026 Microsoft / CSL / Meta drawdowns are textbook examples - the model
was already pointing UP from January as reality kept falling another 30%.

Empirical research (e.g. de Bondt & Thaler) shows that mean reversion
DOES eventually happen on quality stocks, but the timing is so noisy
that "buy the dip" via a 90-day forecast is a coin flip at best, and
asymmetric on the downside (a 30% drop needs a 43% recovery just to
break even).

Design notes
------------
- Pure function on a price DataFrame; no streamlit / yfinance imports.
- "Triggered" uses a simple rule: latest close vs the maximum close in
  the last `window_days` trading days. Default window = 30 (about 6
  weeks of trading), default threshold = -15%.
- The breaker NEVER creates a new GO signal - it only suppresses one.
  Same philosophy as macro confirmation: this is a safety filter, not
  an entry generator.
- We expose the peak date and recovery percentage required so the UI
  can explain WHY a stock was blocked, not just THAT it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# Tunable defaults - exported so tests + Strategy Lab UI can reference them.
DEFAULT_WINDOW_DAYS = 30
DEFAULT_THRESHOLD_PCT = 15.0


@dataclass
class CircuitBreakerStatus:
    """Result of a drawdown check."""

    triggered: bool
    drawdown_pct: float                 # negative number, e.g. -22.5
    peak_date: Optional[pd.Timestamp]
    peak_price: Optional[float]
    current_price: float
    recovery_needed_pct: float          # +X% required to get back to peak
    window_days: int
    threshold_pct: float
    interpretation: str


def check_drawdown(
    df: pd.DataFrame,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> CircuitBreakerStatus:
    """Compute the recent drawdown and decide whether to trip the breaker.

    Parameters
    ----------
    df : columns = date, open, high, low, close, volume; ascending date.
    window_days : how far back to look for the peak. Default 30 trading days
        (~6 weeks). Shorter = more reactive; longer = more conservative.
    threshold_pct : drawdown magnitude (positive number, in percent) at or
        beyond which the breaker trips. Default 15.

    Returns
    -------
    CircuitBreakerStatus - dataclass with `triggered`, drawdown details,
    and a human-readable `interpretation` string suitable for surfacing in
    the UI.
    """
    if df is None or len(df) == 0:
        return CircuitBreakerStatus(
            triggered=False,
            drawdown_pct=0.0,
            peak_date=None,
            peak_price=None,
            current_price=0.0,
            recovery_needed_pct=0.0,
            window_days=window_days,
            threshold_pct=threshold_pct,
            interpretation="No price data available - breaker idle.",
        )

    last_price = float(df["close"].iloc[-1])

    if len(df) < max(2, window_days // 3):
        return CircuitBreakerStatus(
            triggered=False,
            drawdown_pct=0.0,
            peak_date=None,
            peak_price=None,
            current_price=last_price,
            recovery_needed_pct=0.0,
            window_days=window_days,
            threshold_pct=threshold_pct,
            interpretation=(
                f"Only {len(df)} bars of history - not enough to evaluate a "
                f"{window_days}-day drawdown. Breaker idle."
            ),
        )

    window = df.tail(window_days)
    peak_idx = window["close"].idxmax()
    peak_price = float(window.loc[peak_idx, "close"])
    peak_date = pd.Timestamp(window.loc[peak_idx, "date"])

    drawdown_pct = (last_price / peak_price - 1.0) * 100.0  # negative if down
    recovery_needed_pct = (peak_price / last_price - 1.0) * 100.0  # positive

    triggered = drawdown_pct <= -threshold_pct

    if triggered:
        days_since_peak = (pd.Timestamp(df["date"].iloc[-1]) - peak_date).days
        interp = (
            f"Down {drawdown_pct:.1f}% from a peak of {peak_price:.2f} on "
            f"{peak_date.date()} ({days_since_peak} days ago). Would need "
            f"+{recovery_needed_pct:.1f}% to recover. Statistical models "
            f"systematically misjudge falling-knife situations - the breaker "
            f"forces WAIT until the drawdown is shallower than {threshold_pct:.0f}%."
        )
    else:
        interp = (
            f"Recent drawdown {drawdown_pct:.1f}% from peak {peak_price:.2f} on "
            f"{peak_date.date()}. Below the {threshold_pct:.0f}% breaker "
            f"threshold - GO signals not blocked."
        )

    return CircuitBreakerStatus(
        triggered=triggered,
        drawdown_pct=drawdown_pct,
        peak_date=peak_date,
        peak_price=peak_price,
        current_price=last_price,
        recovery_needed_pct=recovery_needed_pct,
        window_days=window_days,
        threshold_pct=threshold_pct,
        interpretation=interp,
    )
