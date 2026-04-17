"""GARCH volatility forecasting (Enhancement #1).

Most simple risk measures (e.g. trailing stdev) treat volatility as constant,
but real markets cluster: a calm month tends to be followed by a calm month,
a stormy week by another stormy week. GARCH(1,1) explicitly models this
clustering and forecasts the next N days of volatility, not just the
current level.

We use this for two things:
  1. Position sizing: shrink positions when GARCH expects above-trend vol,
     grow them when GARCH expects calm. Net effect: more even risk per trade.
  2. Confidence interval breathing: widen forecast bands during expected-vol
     spikes, narrow them during expected calm. Honest CI coverage improves.

Falls back gracefully to a rolling-stdev estimate if the `arch` package is
not installed (e.g. a stripped-down deploy).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from arch import arch_model  # type: ignore

    _ARCH_AVAILABLE = True
except ImportError:
    _ARCH_AVAILABLE = False


def is_arch_available() -> bool:
    return _ARCH_AVAILABLE


@dataclass
class VolatilityForecast:
    """Forecast of future volatility over a horizon."""

    horizon_days: int
    expected_period_vol: float       # forecast std dev over the WHOLE horizon
    expected_annualised_vol: float   # annualised equivalent
    trailing_annualised_vol: float   # for comparison: simple trailing 90-day stdev
    vol_ratio: float                 # forecast / trailing  (>1 = market expected to get noisier)
    method: str                      # "garch(1,1)" or "rolling-stdev-fallback"
    interpretation: str

    @property
    def is_above_trend(self) -> bool:
        return self.vol_ratio > 1.10

    @property
    def is_below_trend(self) -> bool:
        return self.vol_ratio < 0.90


def _trailing_vol(returns: pd.Series, window: int = 90) -> float:
    if len(returns) < window:
        window = max(20, len(returns))
    return float(returns.tail(window).std() * np.sqrt(252))


def forecast_vol(df: pd.DataFrame, *, horizon_days: int = 90) -> VolatilityForecast:
    """Forecast volatility for the next `horizon_days`.

    Uses GARCH(1,1) on percent returns when `arch` is installed, otherwise
    a rolling-stdev fallback.
    """
    returns = df["close"].pct_change().dropna() * 100  # arch likes %-returns
    trailing_ann = _trailing_vol(df["close"].pct_change().dropna(), window=90)

    if not _ARCH_AVAILABLE or len(returns) < 252:
        period_vol = (trailing_ann / np.sqrt(252)) * np.sqrt(horizon_days)
        return VolatilityForecast(
            horizon_days=horizon_days,
            expected_period_vol=float(period_vol),
            expected_annualised_vol=float(trailing_ann),
            trailing_annualised_vol=float(trailing_ann),
            vol_ratio=1.0,
            method="rolling-stdev-fallback",
            interpretation=(
                "GARCH library unavailable - using trailing 90-day stdev as "
                "the volatility forecast (no clustering signal)."
            ),
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = arch_model(returns.values, vol="GARCH", p=1, q=1, mean="zero", rescale=False)
            res = model.fit(disp="off", show_warning=False)
            f = res.forecast(horizon=horizon_days, reindex=False)
            daily_var = f.variance.values[-1]              # length = horizon_days
            cumulative_var = float(np.sum(daily_var)) / 10000.0  # convert from %^2 to decimal^2
            period_vol = float(np.sqrt(cumulative_var))
            avg_daily_vol_pct = float(np.sqrt(np.mean(daily_var)))  # in %
            ann_vol = avg_daily_vol_pct / 100 * np.sqrt(252)
    except Exception as e:  # noqa: BLE001
        logger.warning("GARCH fit failed: %s; falling back to rolling stdev.", e)
        period_vol = (trailing_ann / np.sqrt(252)) * np.sqrt(horizon_days)
        return VolatilityForecast(
            horizon_days=horizon_days,
            expected_period_vol=float(period_vol),
            expected_annualised_vol=float(trailing_ann),
            trailing_annualised_vol=float(trailing_ann),
            vol_ratio=1.0,
            method="rolling-stdev-fallback",
            interpretation=f"GARCH fit failed ({type(e).__name__}); using trailing stdev.",
        )

    ratio = ann_vol / trailing_ann if trailing_ann > 0 else 1.0
    if ratio > 1.10:
        interp = (
            f"GARCH expects the next {horizon_days} days to be ~{(ratio - 1) * 100:.0f}% "
            "noisier than the trailing 90-day average. Tighten position sizes."
        )
    elif ratio < 0.90:
        interp = (
            f"GARCH expects the next {horizon_days} days to be ~{(1 - ratio) * 100:.0f}% "
            "calmer than the trailing 90-day average. Position sizes can be a bit larger."
        )
    else:
        interp = (
            f"GARCH expects the next {horizon_days} days to look like the recent "
            "average - no clustering signal worth acting on."
        )

    return VolatilityForecast(
        horizon_days=horizon_days,
        expected_period_vol=float(period_vol),
        expected_annualised_vol=float(ann_vol),
        trailing_annualised_vol=float(trailing_ann),
        vol_ratio=float(ratio),
        method="garch(1,1)",
        interpretation=interp,
    )


def garch_position_multiplier(vf: VolatilityForecast) -> float:
    """How much to scale position size when GARCH is active.

    > 1.0 = increase size (calm expected)
    < 1.0 = shrink size (storm expected)
    Capped to [0.5, 1.5] so the toggle never produces wild swings.
    """
    if vf.vol_ratio <= 0:
        return 1.0
    multiplier = 1.0 / vf.vol_ratio
    return float(np.clip(multiplier, 0.5, 1.5))


def garch_band_multiplier(vf: VolatilityForecast) -> float:
    """How much to scale forecast CI bands when GARCH is active.

    > 1.0 = widen bands (storm expected, model less certain)
    < 1.0 = tighten bands (calm expected)
    Capped to [0.7, 1.5].
    """
    return float(np.clip(vf.vol_ratio, 0.7, 1.5))
