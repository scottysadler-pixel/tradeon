"""'How to actually place this trade' generator.

Given a GO signal, produces a 6-step plain-English walkthrough tailored
to the user's chosen broker. Used in a Streamlit expander next to every
green signal so a beginner has zero ambiguity about what to actually do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .costs import BROKERS, trade_fee
from .signals import TradeSignal
from .tickers import Ticker


@dataclass
class TradeWalkthrough:
    steps: list[str]
    summary: str
    broker: str


def generate(
    signal: TradeSignal,
    ticker: Ticker,
    *,
    capital_aud: float,
    broker: str = "Stake",
    spot_price_aud: float | None = None,
) -> TradeWalkthrough:
    """Build the step-by-step trade plan."""
    bp = BROKERS[broker]
    spot = spot_price_aud or signal.suggested_entry_price or 0.0

    fee_one_way = trade_fee(capital_aud, ticker.market, broker)
    expected_round_trip = fee_one_way * 2

    shares_can_buy = int(capital_aud // spot) if spot > 0 else 0
    actual_capital = shares_can_buy * spot
    suggested_limit = spot * 1.005   # +0.5% buffer
    suggested_limit_text = f"A${suggested_limit:,.2f}" if ticker.currency == "AUD" else f"~A${suggested_limit:,.2f} (USD equivalent)"

    exit_text = (
        signal.suggested_exit_date.strftime("%a %d %b %Y")
        if signal.suggested_exit_date
        else "(set in your calendar based on the suggested hold window)"
    )
    stop_text = f"A${signal.suggested_stop_price:,.2f}" if signal.suggested_stop_price else "see Stop-Loss section"

    steps = [
        f"**Step 1 - Open your {bp.name} account.** {bp.description}",
        (
            f"**Step 2 - Search for the ticker `{ticker.symbol}`** "
            f"({ticker.name}, {ticker.market})."
        ),
        (
            f"**Step 3 - Choose a LIMIT order** at {suggested_limit_text} "
            "(slightly above current price to ensure you get filled, but not "
            "chasing a runaway). Avoid market orders - they can get filled at "
            "an unexpected price during opening minutes."
        ),
        (
            f"**Step 4 - Order size: {shares_can_buy} shares "
            f"(~A${actual_capital:,.0f})** out of your A${capital_aud:,.0f} "
            f"budget. Estimated total fees for round-trip: A${expected_round_trip:,.2f}."
        ),
        (
            f"**Step 5 - Set a calendar reminder** to review/sell on **{exit_text}**. "
            "The signal expires then; even if the price hasn't moved, exit and "
            "free up the capital."
        ),
        (
            f"**Step 6 - Set a stop-loss alert at {stop_text}.** "
            f"{bp.name} usually lets you set a price alert for free. If price "
            "hits this level, sell - capital preservation matters more than "
            "hoping for a bounce."
        ),
    ]

    summary = (
        f"Plan: BUY {shares_can_buy} x {ticker.symbol} at ~{suggested_limit_text} "
        f"via {bp.name}, exit on {exit_text}, stop at {stop_text}."
    )

    return TradeWalkthrough(steps=steps, summary=summary, broker=broker)


def static_template_help(broker: str = "Stake") -> list[str]:
    """A generic primer that's always shown on the Learn page."""
    bp = BROKERS[broker]
    return [
        f"You're using **{bp.name}** in this example. {bp.description}",
        "**Limit vs Market orders.** A limit order says 'only buy if the price is at or below A$X' - safer, but the trade might not happen. A market order says 'buy now at whatever the current price is' - faster, but you don't control the exact price.",
        "**T+2 settlement.** When you sell, the cash takes 2 business days to land in your account. Plan for this.",
        "**ASX trading hours: 10:00 - 16:00 AEST/AEDT.** Outside these hours, orders queue up for the next session.",
        "**US trading hours in AU time:** roughly 00:30 - 07:00 AEST (varies with daylight saving). Most retail brokers route US trades through these hours; some offer pre/post-market.",
        "**CGT discount cliff.** Hold a share for at least 12 months and you only pay tax on HALF the capital gain. Selling after 11 months and 29 days = full tax. The app's net-return numbers account for this.",
    ]
