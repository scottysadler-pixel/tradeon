"""Australian broker fees and CGT logic.

All trade outcomes in TRADEON are reported NET of these costs so the
trust grade reflects real-world dollars, not theoretical ones.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerFeeProfile:
    name: str
    description: str
    asx_fee: float          # AUD per ASX trade
    asx_pct: float          # additional % of trade value (0.0 if pure flat)
    us_fee_aud: float       # AUD per US trade (after FX)
    us_pct: float           # additional %
    chess_sponsored: bool   # CHESS = you legally own the shares directly


BROKERS: dict[str, BrokerFeeProfile] = {
    "CommSec": BrokerFeeProfile(
        name="CommSec",
        description="CommBank's broker. Higher fees but established, CHESS-sponsored ASX.",
        asx_fee=10.0,       # CommSec base fee for trades up to $1k
        asx_pct=0.0,
        us_fee_aud=19.95,
        us_pct=0.0,
        chess_sponsored=True,
    ),
    "Stake": BrokerFeeProfile(
        name="Stake",
        description="Low-cost. CHESS-sponsored ASX, custodial US (cheaper, but you don't directly hold US shares).",
        asx_fee=3.0,
        asx_pct=0.0,
        us_fee_aud=3.0,
        us_pct=0.0,
        chess_sponsored=True,
    ),
    "Pearler": BrokerFeeProfile(
        name="Pearler",
        description="Long-term-focused. CHESS-sponsored ASX. Decent fees.",
        asx_fee=6.50,
        asx_pct=0.0,
        us_fee_aud=6.50,
        us_pct=0.0,
        chess_sponsored=True,
    ),
    "SelfWealth": BrokerFeeProfile(
        name="SelfWealth",
        description="Flat fee, CHESS-sponsored ASX.",
        asx_fee=9.50,
        asx_pct=0.0,
        us_fee_aud=9.50,
        us_pct=0.0,
        chess_sponsored=True,
    ),
}

DEFAULT_BROKER = "Stake"


def trade_fee(trade_value_aud: float, market: str, broker: str = DEFAULT_BROKER) -> float:
    """Total fee in AUD for a single buy or sell."""
    bp = BROKERS[broker]
    if market == "ASX":
        return bp.asx_fee + (bp.asx_pct * trade_value_aud)
    return bp.us_fee_aud + (bp.us_pct * trade_value_aud)


def round_trip_fees(trade_value_aud: float, market: str, broker: str = DEFAULT_BROKER) -> float:
    """Buy + sell fee in AUD for a complete trade."""
    return 2 * trade_fee(trade_value_aud, market, broker)


# --- Australian CGT (Capital Gains Tax) ---
# Simplified: assumes individual taxpayer, top marginal rate as upper bound.
# We display BOTH pre-tax and post-tax outcomes; this is just for the
# 'rough net return' headline number.

CGT_DISCOUNT_DAYS = 365  # >12 months held = 50% CGT discount
DEFAULT_MARGINAL_RATE = 0.325  # 32.5% bracket - mid-range working Australian


def cgt_on_gain(
    gain_aud: float,
    held_days: int,
    marginal_rate: float = DEFAULT_MARGINAL_RATE,
) -> float:
    """CGT payable on a realised gain in AUD.

    Negative gains (losses) return 0 - losses can offset other gains but we
    don't model that here.
    """
    if gain_aud <= 0:
        return 0.0
    taxable = gain_aud
    if held_days >= CGT_DISCOUNT_DAYS:
        taxable = gain_aud * 0.5  # 50% discount
    return taxable * marginal_rate


def net_trade_outcome(
    buy_price_aud: float,
    sell_price_aud: float,
    shares: int,
    held_days: int,
    market: str,
    broker: str = DEFAULT_BROKER,
    marginal_rate: float = DEFAULT_MARGINAL_RATE,
) -> dict:
    """Compute the full economics of a single trade.

    Returns gross gain, fees, tax and net AUD outcome.
    """
    buy_value = buy_price_aud * shares
    sell_value = sell_price_aud * shares
    fees = trade_fee(buy_value, market, broker) + trade_fee(sell_value, market, broker)
    gross_gain = sell_value - buy_value
    gain_after_fees = gross_gain - fees
    tax = cgt_on_gain(gain_after_fees, held_days, marginal_rate)
    net = gain_after_fees - tax
    return {
        "buy_value_aud": buy_value,
        "sell_value_aud": sell_value,
        "gross_gain_aud": gross_gain,
        "fees_aud": fees,
        "tax_aud": tax,
        "net_gain_aud": net,
        "net_return_pct": (net / buy_value) * 100 if buy_value else 0.0,
        "qualified_for_cgt_discount": held_days >= CGT_DISCOUNT_DAYS,
    }
