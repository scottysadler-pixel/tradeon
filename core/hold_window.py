"""Best-historical-hold-window finder.

For each stock, scans 20 years of history for the (buy month, sell month)
combination that produced the most consistent gains. This is the headline
short/medium-term insight - 'buy late October, sell late February' style.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HoldWindow:
    buy_month: int
    sell_month: int
    avg_return_pct: float
    median_return_pct: float
    hit_rate_pct: float
    worst_case_pct: float
    best_case_pct: float
    n_years: int
    holding_days: int

    @property
    def description(self) -> str:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return (
            f"Buy {months[self.buy_month - 1]}, sell {months[self.sell_month - 1]}: "
            f"avg {self.avg_return_pct:+.1f}%, hit-rate {self.hit_rate_pct:.0f}% "
            f"over {self.n_years} years"
        )


def _month_close_series(df: pd.DataFrame) -> pd.DataFrame:
    """Resample to month-end close, return df with year/month columns."""
    s = df.set_index("date")["close"].resample("ME").last().dropna()
    out = pd.DataFrame({"close": s.values, "date": s.index})
    out["year"] = out["date"].dt.year
    out["month"] = out["date"].dt.month
    return out


def _trade_returns(monthly: pd.DataFrame, buy_m: int, sell_m: int) -> list[float]:
    """For every historical year, compute return of (buy at end of buy_m, sell at end of sell_m).

    If sell_m <= buy_m, the trade crosses year-end (buy this year, sell next year).
    """
    returns: list[float] = []
    by_year_month = monthly.set_index(["year", "month"])["close"]

    years = sorted(monthly["year"].unique())
    for y in years:
        try:
            buy_price = by_year_month.loc[(y, buy_m)]
            if sell_m > buy_m:
                sell_price = by_year_month.loc[(y, sell_m)]
            else:
                sell_price = by_year_month.loc[(y + 1, sell_m)]
            if buy_price > 0 and sell_price > 0:
                returns.append((sell_price / buy_price) - 1)
        except KeyError:
            continue
    return returns


def _summarise(buy_m: int, sell_m: int, returns: list[float]) -> HoldWindow | None:
    if len(returns) < 5:  # need at least 5 years of data to be meaningful
        return None
    arr = np.array(returns)
    holding = (sell_m - buy_m) % 12 or 12
    return HoldWindow(
        buy_month=buy_m,
        sell_month=sell_m,
        avg_return_pct=float(arr.mean() * 100),
        median_return_pct=float(np.median(arr) * 100),
        hit_rate_pct=float((arr > 0).mean() * 100),
        worst_case_pct=float(arr.min() * 100),
        best_case_pct=float(arr.max() * 100),
        n_years=len(arr),
        holding_days=holding * 30,
    )


def best_windows(
    df: pd.DataFrame,
    min_hold_months: int = 1,
    max_hold_months: int = 6,
    top_n: int = 5,
    min_hit_rate_pct: float = 60.0,
) -> list[HoldWindow]:
    """Return the top-N historical hold-windows ranked by risk-adjusted return.

    Risk-adjusted = avg_return * hit_rate (rewards both magnitude AND consistency).
    Only considers windows of `min_hold_months` to `max_hold_months` length.
    """
    monthly = _month_close_series(df)
    if monthly.empty:
        return []

    candidates: list[HoldWindow] = []
    for buy_m in range(1, 13):
        for hold in range(min_hold_months, max_hold_months + 1):
            sell_m = ((buy_m - 1 + hold) % 12) + 1
            rets = _trade_returns(monthly, buy_m, sell_m)
            window = _summarise(buy_m, sell_m, rets)
            if window and window.hit_rate_pct >= min_hit_rate_pct:
                candidates.append(window)

    candidates.sort(
        key=lambda w: w.avg_return_pct * (w.hit_rate_pct / 100),
        reverse=True,
    )
    return candidates[:top_n]


def all_windows_matrix(
    df: pd.DataFrame,
    min_hold_months: int = 1,
    max_hold_months: int = 6,
) -> pd.DataFrame:
    """12x6 matrix of avg returns for every (buy_month, hold_length) combination.

    Used for the heatmap on the Deep Dive page.
    """
    monthly = _month_close_series(df)
    rows = []
    for buy_m in range(1, 13):
        row = {"buy_month": buy_m}
        for hold in range(min_hold_months, max_hold_months + 1):
            sell_m = ((buy_m - 1 + hold) % 12) + 1
            rets = _trade_returns(monthly, buy_m, sell_m)
            row[f"{hold}m"] = (np.mean(rets) * 100) if rets else None
        rows.append(row)
    return pd.DataFrame(rows)


def upcoming_window(
    df: pd.DataFrame,
    current_month: int,
    *,
    min_hit_rate_pct: float = 60.0,
) -> HoldWindow | None:
    """Is THIS month a historically good time to buy this stock?

    Returns the best window starting in `current_month`, or None if no
    statistically promising window starts now.
    """
    monthly = _month_close_series(df)
    if monthly.empty:
        return None

    best: HoldWindow | None = None
    for hold in range(1, 7):
        sell_m = ((current_month - 1 + hold) % 12) + 1
        rets = _trade_returns(monthly, current_month, sell_m)
        window = _summarise(current_month, sell_m, rets)
        if window and window.hit_rate_pct >= min_hit_rate_pct:
            score = window.avg_return_pct * (window.hit_rate_pct / 100)
            best_score = (
                best.avg_return_pct * (best.hit_rate_pct / 100) if best else -1e9
            )
            if score > best_score:
                best = window
    return best
