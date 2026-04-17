"""Watchlist correlation matrix and divergence detector.

When two historically co-moving stocks (e.g. BHP and RIO, both iron-ore
miners) suddenly DIVERGE, that's often a meaningful signal worth flagging.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DivergenceFlag:
    pair: tuple[str, str]
    long_term_corr: float
    recent_corr: float
    delta: float
    interpretation: str


def correlation_matrix(returns_by_symbol: dict[str, pd.Series]) -> pd.DataFrame:
    """Pearson correlation of daily returns between every watchlist pair."""
    df = pd.DataFrame(returns_by_symbol)
    return df.corr()


def detect_divergences(
    returns_by_symbol: dict[str, pd.Series],
    *,
    long_window_days: int = 504,    # 2 years
    short_window_days: int = 30,
    pair_min_long_corr: float = 0.6,
    delta_threshold: float = 0.4,
) -> list[DivergenceFlag]:
    """Find historically correlated pairs that have recently diverged."""
    flags: list[DivergenceFlag] = []
    df = pd.DataFrame(returns_by_symbol).dropna(how="all")
    if len(df) < long_window_days:
        return flags

    long_window = df.tail(long_window_days)
    short_window = df.tail(short_window_days)

    long_corr = long_window.corr()
    short_corr = short_window.corr()

    cols = df.columns.tolist()
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            try:
                lc = float(long_corr.loc[a, b])
                sc = float(short_corr.loc[a, b])
            except KeyError:
                continue
            if np.isnan(lc) or np.isnan(sc):
                continue
            if lc < pair_min_long_corr:
                continue
            delta = sc - lc
            if abs(delta) < delta_threshold:
                continue
            interp = (
                f"{a} and {b} have a long-term correlation of {lc:.2f} but only "
                f"{sc:.2f} over the last {short_window_days} days. They are "
                f"{'decoupling' if delta < 0 else 'tightening'} - worth a look."
            )
            flags.append(DivergenceFlag(
                pair=(a, b),
                long_term_corr=lc,
                recent_corr=sc,
                delta=delta,
                interpretation=interp,
            ))
    return flags
