"""Volatility-adjusted position sizing.

Simple principle: the same expected % return on a calmer stock should get
a larger dollar allocation than on a wilder stock, so each position
contributes similar risk to the portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass

from .analysis import annualised_volatility


@dataclass
class PositionSize:
    suggested_aud: float
    shares: int
    pct_of_capital: float
    explanation: str


def suggest(
    capital_aud: float,
    spot_price_aud: float,
    df,
    *,
    target_risk_pct: float = 1.5,
    max_pct_of_capital: float = 25.0,
) -> PositionSize:
    """Suggest position size in AUD and shares.

    `target_risk_pct` is how much of total capital you're willing to lose if
    the stop-loss triggers (we treat 1 standard deviation move as the risk
    unit). Default 1.5% per trade is conservative.
    """
    vol = annualised_volatility(df) or 0.30  # fallback 30%
    # Convert annualised vol to a 90-day vol estimate (sqrt-time)
    period_vol = vol * (90 / 252) ** 0.5
    if period_vol <= 0:
        period_vol = 0.10

    risk_unit_pct = period_vol * 100  # e.g. 18% expected 90-day swing
    pct_of_capital = (target_risk_pct / risk_unit_pct) * 100
    pct_of_capital = min(pct_of_capital, max_pct_of_capital)

    suggested = capital_aud * (pct_of_capital / 100)
    shares = int(suggested // spot_price_aud) if spot_price_aud > 0 else 0
    actual_aud = shares * spot_price_aud

    return PositionSize(
        suggested_aud=actual_aud,
        shares=shares,
        pct_of_capital=(actual_aud / capital_aud) * 100 if capital_aud else 0,
        explanation=(
            f"This stock has shown ~{risk_unit_pct:.0f}% typical 90-day swings. "
            f"To risk no more than {target_risk_pct:.1f}% of your A${capital_aud:,.0f} "
            f"capital on this trade, allocate ~A${actual_aud:,.0f} "
            f"({shares} shares at A${spot_price_aud:,.2f})."
        ),
    )
