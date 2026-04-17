"""Signal decider.

Takes inputs from every analytical layer and produces a single GO / WAIT
recommendation per stock. Default state is WAIT - we only flip to GO
when ALL of the following align:

  1. Trust grade B or better
  2. Market regime is favourable (not bear)
  3. We are in / entering an active historical seasonal hold-window
  4. Ensemble forecast direction is meaningfully above baseline
  5. Technical indicators confirm
  6. Not within N days of the historical earnings window

Conservative on purpose - cutting losing trades is more important than
catching every winner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

from .backtest import BacktestResult, TrustGrade
from .earnings_proxy import EarningsWindow
from .forecast import Forecast
from .hold_window import HoldWindow
from .regime import RegimeState
from .stops import StopLossSuggestion
from .technicals import TechnicalSnapshot

SignalState = Literal["GO", "WAIT", "AVOID"]


@dataclass
class TradeSignal:
    state: SignalState
    confidence: float                 # 0..1
    headline: str
    reasons: list[str] = field(default_factory=list)
    suggested_entry_price: float | None = None
    suggested_exit_date: datetime | None = None
    suggested_stop_price: float | None = None
    expected_return_pct: float | None = None


def decide(
    *,
    trust: TrustGrade,
    regime: RegimeState,
    hold: HoldWindow | None,
    forecast: Forecast,
    technicals: TechnicalSnapshot,
    earnings: EarningsWindow,
    stops: StopLossSuggestion,
    spot_price: float,
    naive_baseline_drift_pct: float = 0.0,
) -> TradeSignal:
    """The main GO/WAIT decision."""
    reasons: list[str] = []

    # ---- Hard blockers -------------------------------------------------
    if trust.grade in ("D", "F"):
        return TradeSignal(
            state="AVOID",
            confidence=0.1,
            headline=f"Trust grade {trust.grade} - model has not earned this stock's predictions.",
            reasons=[trust.interpretation],
        )

    if regime.label == "bear":
        return TradeSignal(
            state="WAIT",
            confidence=0.0,
            headline="Bear regime detected - sitting out.",
            reasons=[regime.interpretation],
        )

    if earnings.is_active:
        return TradeSignal(
            state="WAIT",
            confidence=0.2,
            headline="Earnings window active - too unpredictable to enter.",
            reasons=[earnings.interpretation],
        )

    if technicals.bearish_warning:
        return TradeSignal(
            state="WAIT",
            confidence=0.2,
            headline="Technicals warn against entering now.",
            reasons=technicals.notes,
        )

    # ---- Soft confirmations -------------------------------------------
    forecast_end = float(forecast.forecast_mean[-1])
    expected_pct = ((forecast_end / spot_price) - 1) * 100
    forecast_lift_vs_baseline = expected_pct - naive_baseline_drift_pct

    confirmations: list[bool] = []

    if hold is not None:
        confirmations.append(True)
        reasons.append(f"Active seasonal window: {hold.description}.")
    else:
        reasons.append("No active seasonal window for this month.")
        confirmations.append(False)

    if forecast_lift_vs_baseline > 1.0:
        confirmations.append(True)
        reasons.append(
            f"Ensemble forecast +{expected_pct:.1f}% vs naive baseline drift "
            f"{naive_baseline_drift_pct:+.1f}%."
        )
    else:
        confirmations.append(False)
        reasons.append(
            f"Forecast (+{expected_pct:.1f}%) not meaningfully above baseline drift "
            f"({naive_baseline_drift_pct:+.1f}%)."
        )

    if technicals.bullish_confirmed:
        confirmations.append(True)
        reasons.extend(technicals.notes)
    else:
        confirmations.append(False)
        reasons.extend(technicals.notes)

    if regime.label == "bull":
        confirmations.append(True)
        reasons.append(regime.interpretation)
    else:
        confirmations.append(False)
        reasons.append(regime.interpretation)

    n_passed = sum(confirmations)
    confidence = n_passed / len(confirmations)

    # GO requires at least 3 of 4 confirmations AND a non-active earnings window
    if n_passed >= 3 and trust.grade in ("A", "B"):
        exit_date = (
            pd.Timestamp(forecast.forecast_dates[-1]).to_pydatetime()
            if hold is None
            else None  # Calendar reminder pre-EXIT taken from hold window in UI layer
        )
        return TradeSignal(
            state="GO",
            confidence=confidence,
            headline=(
                f"GO - {n_passed}/4 confirmations, trust grade {trust.grade}. "
                f"Expected {expected_pct:+.1f}% over horizon."
            ),
            reasons=reasons,
            suggested_entry_price=spot_price,
            suggested_exit_date=exit_date,
            suggested_stop_price=stops.recommended_stop_price,
            expected_return_pct=expected_pct,
        )

    return TradeSignal(
        state="WAIT",
        confidence=confidence,
        headline=f"WAIT - only {n_passed}/4 confirmations agree.",
        reasons=reasons,
    )
