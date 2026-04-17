"""Earnings-window detector - inferred from price alone.

We don't pull earnings calendars (that would be external data). Instead
we detect the recurring volatility-spike clusters that occur every ~90
days for most listed companies (which usually correspond to quarterly
earnings releases). The signal decider then warns against entering
within N days of the next predicted spike.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


@dataclass
class EarningsWindow:
    typical_spike_months: list[int]
    avg_days_between: float
    next_window_estimate: datetime | None
    is_active: bool
    days_until_next: int | None
    interpretation: str


def _abs_returns(df: pd.DataFrame) -> pd.Series:
    s = df.set_index("date")["close"].pct_change().abs().dropna()
    return s


def _identify_spikes(returns: pd.Series, z_threshold: float = 2.5) -> pd.DatetimeIndex:
    """Days where |return| was z_threshold standard deviations above mean."""
    rolling_std = returns.rolling(60).std()
    rolling_mean = returns.rolling(60).mean()
    z = (returns - rolling_mean) / rolling_std.replace(0, np.nan)
    return returns.index[z > z_threshold]


def detect(df: pd.DataFrame, days_buffer: int = 5) -> EarningsWindow:
    """Detect the typical earnings-spike pattern from price alone.

    `days_buffer` is how many days before/after a predicted spike date we
    consider the window 'active' (and therefore avoid entering trades).
    """
    if len(df) < 252:
        return EarningsWindow([], 0, None, False, None,
                              "Not enough history to detect earnings pattern.")

    returns = _abs_returns(df)
    spikes = _identify_spikes(returns)
    if len(spikes) < 4:
        return EarningsWindow([], 0, None, False, None,
                              "No clear earnings-volatility pattern detected.")

    # Which calendar months historically host spikes?
    months = pd.Series(spikes.month).value_counts().sort_values(ascending=False)
    typical_months = months.head(4).index.tolist()

    # Average gap between spike events
    gaps = pd.Series(spikes).diff().dropna().dt.days
    avg_gap = float(gaps.median()) if not gaps.empty else 0

    # Project the next spike: latest spike + median gap
    last_spike = pd.Timestamp(spikes.max())
    next_spike = last_spike + timedelta(days=int(avg_gap)) if avg_gap > 0 else None
    today = pd.Timestamp(datetime.today().date())

    # If next projected spike is in the past (we missed observing it), step forward
    while next_spike is not None and next_spike < today - timedelta(days=days_buffer):
        next_spike = next_spike + timedelta(days=int(avg_gap))

    days_until = (next_spike - today).days if next_spike else None
    is_active = days_until is not None and -days_buffer <= days_until <= days_buffer

    if is_active:
        interp = (
            f"Within ~{days_buffer}-day window of a likely earnings event "
            f"(estimated {next_spike.strftime('%d %b %Y') if next_spike else 'soon'}). "
            "Avoid opening new positions - earnings can move price unpredictably."
        )
    elif days_until is not None and days_until > days_buffer:
        interp = (
            f"Next likely earnings window in ~{days_until} days "
            f"({next_spike.strftime('%d %b %Y') if next_spike else 'unknown'}). "
            "Plan trade exits around this date."
        )
    else:
        interp = "No earnings window currently active."

    return EarningsWindow(
        typical_spike_months=sorted(typical_months),
        avg_days_between=avg_gap,
        next_window_estimate=next_spike.to_pydatetime() if next_spike is not None else None,
        is_active=is_active,
        days_until_next=days_until,
        interpretation=interp,
    )
