"""Market regime detection.

Two-state Hidden Markov Model on log returns labels each historical day
as 'risk-on' (calm/uptrend) or 'risk-off' (volatile/downtrend). We then
post-process for a third 'sideways' label when neither extreme is clear.

Used to (a) condition forecasts on similar-regime history, and (b) gate
GO signals - we don't act in detected bear regimes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

logger = logging.getLogger(__name__)

RegimeLabel = Literal["bull", "bear", "sideways"]


@dataclass
class RegimeState:
    label: RegimeLabel
    confidence: float
    days_in_regime: int
    interpretation: str


def _fit_hmm(returns: np.ndarray) -> tuple[GaussianHMM, np.ndarray]:
    model = GaussianHMM(
        n_components=2,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(returns.reshape(-1, 1))
    states = model.predict(returns.reshape(-1, 1))
    return model, states


def detect_regime(df: pd.DataFrame) -> RegimeState:
    """Detect current regime from price history.

    Returns the current regime label, model confidence, days in this regime,
    and a plain-English interpretation.
    """
    if len(df) < 252:
        return RegimeState(
            label="sideways",
            confidence=0.0,
            days_in_regime=0,
            interpretation="Not enough history to detect a regime.",
        )

    returns = df["close"].pct_change().dropna().values
    if len(returns) < 100:
        return RegimeState(
            label="sideways",
            confidence=0.0,
            days_in_regime=0,
            interpretation="Not enough returns data.",
        )

    try:
        model, states = _fit_hmm(returns)
    except Exception as e:  # noqa: BLE001
        logger.warning("HMM fit failed: %s; falling back to trend heuristic", e)
        return _fallback_trend_regime(df)

    # Identify which hidden state corresponds to bull vs bear
    means = model.means_.flatten()
    bull_state = int(np.argmax(means))

    current = states[-1]
    bull_today = current == bull_state

    # Run-length: how long have we been in this state?
    run_length = 1
    for s in reversed(states[:-1]):
        if s == current:
            run_length += 1
        else:
            break

    # Posterior probability for the current observation
    proba = model.predict_proba(returns.reshape(-1, 1))[-1]
    confidence = float(proba.max())

    # If the model is unsure (probabilities near 50/50), call it sideways
    if confidence < 0.65:
        label: RegimeLabel = "sideways"
        interp = (
            f"Model is uncertain ({confidence:.0%} confidence). Treating market "
            "as sideways - no strong directional bias detected."
        )
    elif bull_today:
        label = "bull"
        interp = (
            f"Detected bull regime ({confidence:.0%} confidence), "
            f"{run_length} days running. Forecasts trained on similar uptrend "
            "periods will be weighted higher."
        )
    else:
        label = "bear"
        interp = (
            f"Detected bear regime ({confidence:.0%} confidence), "
            f"{run_length} days running. GO signals will be suppressed; bear "
            "markets historically chew up most short-hold strategies."
        )

    return RegimeState(
        label=label,
        confidence=confidence,
        days_in_regime=run_length,
        interpretation=interp,
    )


def _fallback_trend_regime(df: pd.DataFrame) -> RegimeState:
    """Simple fallback: 50-day vs 200-day moving average trend rule."""
    s = df["close"]
    if len(s) < 200:
        return RegimeState("sideways", 0.0, 0, "Insufficient data for fallback.")
    ma50 = s.rolling(50).mean().iloc[-1]
    ma200 = s.rolling(200).mean().iloc[-1]
    spot = s.iloc[-1]
    if spot > ma50 > ma200:
        return RegimeState("bull", 0.6, 0, "Trend-following fallback: bull (price > 50-day > 200-day).")
    if spot < ma50 < ma200:
        return RegimeState("bear", 0.6, 0, "Trend-following fallback: bear (price < 50-day < 200-day).")
    return RegimeState("sideways", 0.5, 0, "Trend-following fallback: mixed signals, sideways.")


def historical_regime_labels(df: pd.DataFrame) -> pd.DataFrame:
    """For each historical day, label its regime. Useful for charting."""
    if len(df) < 252:
        return pd.DataFrame(columns=["date", "regime"])
    returns = df["close"].pct_change().dropna()
    try:
        model, states = _fit_hmm(returns.values)
        means = model.means_.flatten()
        bull_state = int(np.argmax(means))
        labels = ["bull" if s == bull_state else "bear" for s in states]
        return pd.DataFrame({"date": returns.index.values, "regime": labels})
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["date", "regime"])
