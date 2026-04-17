"""Broker convenience links + clipboard-ready order ticket.

Two outputs per active GO signal:

1. A best-effort broker link (broker home or, where reliably possible, the
   symbol page). Broker URL formats change without notice; this module
   prefers the broker's homepage and tells the user to search rather than
   linking to a deep URL that might 404.
2. A reliable Yahoo Finance chart link for sanity-checking the symbol.
3. A clipboard-friendly one-line order ticket the user can paste into
   their broker's order screen or a notes app.

We deliberately do NOT attempt automated order submission - none of the
common AU retail brokers (CommSec, Stake, Pearler, SelfWealth) have a
public retail API, and using reverse-engineered APIs risks account
suspension. See IMPROVEMENTS.md section "About broker integration" for
the full reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .signals import TradeSignal
from .tickers import Ticker


@dataclass(frozen=True)
class BrokerLink:
    label: str
    url: str
    note: str


# Broker homepages (verified safe URLs - won't 404).
# Deep-link patterns to symbol pages are NOT used because broker URL
# schemes change frequently and a broken link is worse than no link.
_BROKER_HOME: dict[str, str] = {
    "CommSec":    "https://www2.commsec.com.au/",
    "Stake":      "https://hellostake.com/au",
    "Pearler":    "https://app.pearler.com/",
    "SelfWealth": "https://app.selfwealth.com.au/",
}


def yahoo_chart_url(ticker: Ticker) -> str:
    """Yahoo Finance quote page. Stable URL - works for both ASX and US."""
    return f"https://finance.yahoo.com/quote/{ticker.symbol}"


def broker_link(broker: str, ticker: Ticker) -> BrokerLink:
    """Best-effort link to the user's broker."""
    home = _BROKER_HOME.get(broker, "")
    return BrokerLink(
        label=f"Open {broker}",
        url=home,
        note=(
            f"Opens {broker}'s site. Once logged in, search for "
            f"`{ticker.symbol}` ({ticker.name})."
        ),
    )


def order_ticket(
    signal: TradeSignal,
    ticker: Ticker,
    *,
    shares: int,
    spot_price_aud: float,
) -> str:
    """One-line order ticket the user copies and pastes.

    Format chosen to be both human-readable AND parseable - if you ever
    paste it into a spreadsheet to start a trade journal, the fields
    are already in a regular order.
    """
    suggested_limit = signal.suggested_entry_price or (spot_price_aud * 1.005)
    stop = signal.suggested_stop_price
    exit_date = signal.suggested_exit_date

    parts = [
        "LIMIT BUY",
        f"{shares} x {ticker.symbol}",
        f"@ A${suggested_limit:,.2f}",
    ]
    if stop:
        parts.append(f"stop @ A${stop:,.2f}")
    if exit_date:
        if isinstance(exit_date, date):
            exit_str = exit_date.strftime("%Y-%m-%d")
        else:
            exit_str = str(exit_date)
        parts.append(f"target exit {exit_str}")
    parts.append(f"({ticker.name}, {ticker.market})")
    return " | ".join(parts)


def confirmation_checklist(signal: TradeSignal, ticker: Ticker) -> list[str]:
    """Three quick visual checks the user should do before submitting."""
    checks = [
        f"Confirm symbol matches: **{ticker.symbol}** = {ticker.name}",
        "Confirm order type is **LIMIT** (not Market) at the suggested price",
    ]
    if signal.suggested_stop_price:
        checks.append(
            f"After fill, place a separate stop-loss alert at "
            f"**A${signal.suggested_stop_price:,.2f}**"
        )
    if signal.suggested_exit_date:
        checks.append(
            f"Add a calendar reminder for **"
            f"{signal.suggested_exit_date.strftime('%a %d %b %Y')}**: "
            "review/sell"
        )
    return checks
