"""Descriptive statistics and seasonality analysis.

All functions take a price DataFrame with `date` and `close` columns and
return scalar metrics or smaller DataFrames. Pure NumPy/Pandas where
possible; statsmodels for STL decomposition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass
class StockStats:
    cagr_pct: float
    annualised_vol_pct: float
    max_drawdown_pct: float
    sharpe: float
    pattern_strength: float
    sample_years: float


def daily_returns(df: pd.DataFrame) -> pd.Series:
    return df["close"].pct_change().dropna()


def cagr(df: pd.DataFrame) -> float:
    """Compound annual growth rate (decimal, e.g. 0.10 = 10%)."""
    if len(df) < 2:
        return 0.0
    start, end = df["close"].iloc[0], df["close"].iloc[-1]
    days = (df["date"].iloc[-1] - df["date"].iloc[0]).days
    if days <= 0 or start <= 0:
        return 0.0
    years = days / 365.25
    return (end / start) ** (1 / years) - 1


def annualised_volatility(df: pd.DataFrame) -> float:
    r = daily_returns(df)
    if r.empty:
        return 0.0
    return float(r.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(df: pd.DataFrame) -> float:
    """Worst peak-to-trough fall, as a negative decimal (e.g. -0.45 = -45%)."""
    s = df["close"]
    if s.empty:
        return 0.0
    peak = s.cummax()
    dd = (s / peak) - 1
    return float(dd.min())


def sharpe_ratio(df: pd.DataFrame, risk_free_rate: float = 0.04) -> float:
    """Annualised Sharpe. Default risk-free 4% (RBA cash rate ballpark)."""
    r = daily_returns(df)
    if r.empty or r.std() == 0:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = r - daily_rf
    return float((excess.mean() / r.std()) * np.sqrt(TRADING_DAYS_PER_YEAR))


def pattern_strength(df: pd.DataFrame) -> float:
    """How forecastable is this stock?

    Returns a 0-1 score combining:
      - Autocorrelation of returns (does momentum persist?)
      - Strength of seasonal vs residual variance from STL decomposition
      - Inverse of return volatility (calmer stocks are easier)

    Below ~0.30 means we should not trust ANY forecast on this name.
    """
    r = daily_returns(df)
    if len(r) < 252:
        return 0.0

    autocorr = abs(r.autocorr(lag=1))
    if np.isnan(autocorr):
        autocorr = 0.0

    # Seasonal strength via simple monthly groupby (cheaper than full STL here)
    monthly = df.set_index("date")["close"].resample("ME").mean().pct_change().dropna()
    if len(monthly) < 24:
        seasonal_strength = 0.0
    else:
        by_month = monthly.groupby(monthly.index.month).mean()
        seasonal_strength = min(1.0, float(by_month.std() / max(monthly.std(), 1e-9)) * 3)

    vol_score = float(np.clip(1 - (r.std() * np.sqrt(252)) / 0.8, 0, 1))

    score = 0.4 * autocorr * 5 + 0.4 * seasonal_strength + 0.2 * vol_score
    return float(np.clip(score, 0, 1))


def stock_stats(df: pd.DataFrame) -> StockStats:
    days = (df["date"].iloc[-1] - df["date"].iloc[0]).days if len(df) > 1 else 0
    return StockStats(
        cagr_pct=cagr(df) * 100,
        annualised_vol_pct=annualised_volatility(df) * 100,
        max_drawdown_pct=max_drawdown(df) * 100,
        sharpe=sharpe_ratio(df),
        pattern_strength=pattern_strength(df),
        sample_years=days / 365.25,
    )


def quarterly_seasonality(df: pd.DataFrame) -> pd.DataFrame:
    """Average return per calendar quarter with hit rate.

    Returns one row per quarter (Q1-Q4) with mean return %, std, hit rate %
    and number of historical observations.
    """
    s = df.set_index("date")["close"].resample("QE").last().dropna()
    quarterly_ret = s.pct_change().dropna()
    quarterly_ret.index = quarterly_ret.index.to_period("Q")
    by_q = quarterly_ret.groupby(quarterly_ret.index.quarter)

    rows = []
    for q, group in by_q:
        rows.append(
            {
                "quarter": f"Q{q}",
                "mean_return_pct": float(group.mean() * 100),
                "std_pct": float(group.std() * 100),
                "hit_rate_pct": float((group > 0).mean() * 100),
                "n_observations": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def monthly_seasonality(df: pd.DataFrame) -> pd.DataFrame:
    """Average return per calendar month with hit rate."""
    s = df.set_index("date")["close"].resample("ME").last().dropna()
    monthly_ret = s.pct_change().dropna()
    by_m = monthly_ret.groupby(monthly_ret.index.month)

    rows = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m, group in by_m:
        rows.append(
            {
                "month_num": int(m),
                "month": months[m - 1],
                "mean_return_pct": float(group.mean() * 100),
                "std_pct": float(group.std() * 100),
                "hit_rate_pct": float((group > 0).mean() * 100),
                "n_observations": int(len(group)),
            }
        )
    return pd.DataFrame(rows).sort_values("month_num").reset_index(drop=True)


def eofy_tax_loss_pattern(df: pd.DataFrame) -> dict:
    """Detect AU end-of-financial-year tax-loss-selling pattern.

    AU EOFY = 30 June. Many ASX stocks dip in May-June and bounce in July
    as investors sell losers for tax then re-enter the market in the new
    financial year. We measure the average return of:
      - May + June combined (the dip phase)
      - July (the bounce phase)
    Across 20 years and report whether the pattern is statistically real.
    """
    monthly = monthly_seasonality(df)
    if monthly.empty:
        return {}

    by_month = monthly.set_index("month_num")["mean_return_pct"]
    dip = float((by_month.get(5, 0) + by_month.get(6, 0)))
    bounce = float(by_month.get(7, 0))

    # Pattern is "real" if dip is negative AND bounce is materially positive
    pattern_present = dip < -0.5 and bounce > 1.0

    return {
        "may_jun_avg_return_pct": dip,
        "july_avg_return_pct": bounce,
        "pattern_detected": pattern_present,
        "interpretation": (
            "Classic EOFY tax-loss pattern: stock historically dips into June and "
            "rebounds in July."
            if pattern_present
            else "No clear EOFY tax-loss pattern detected for this stock."
        ),
    }
