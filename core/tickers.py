"""Curated TRADEON watchlist.

Mix of ASX large caps (the user's home market) and US big-tech (where
historical price patterns are unusually clean and forecastable). The trust
grade earned by each stock will determine which are actually traded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Currency = Literal["AUD", "USD"]
Market = Literal["ASX", "NASDAQ", "NYSE"]


@dataclass(frozen=True)
class Ticker:
    symbol: str
    name: str
    sector: str
    market: Market
    currency: Currency

    @property
    def display(self) -> str:
        return f"{self.symbol}  -  {self.name}"


WATCHLIST: list[Ticker] = [
    # ASX miners
    Ticker("BHP.AX",  "BHP Group",                 "Materials",     "ASX",    "AUD"),
    Ticker("RIO.AX",  "Rio Tinto",                 "Materials",     "ASX",    "AUD"),
    Ticker("FMG.AX",  "Fortescue",                 "Materials",     "ASX",    "AUD"),
    Ticker("BSL.AX",  "BlueScope Steel",           "Materials",     "ASX",    "AUD"),
    Ticker("S32.AX",  "South32",                   "Materials",     "ASX",    "AUD"),
    # ASX banks / financials
    Ticker("CBA.AX",  "Commonwealth Bank",         "Financials",    "ASX",    "AUD"),
    Ticker("WBC.AX",  "Westpac Banking",           "Financials",    "ASX",    "AUD"),
    Ticker("NAB.AX",  "National Australia Bank",   "Financials",    "ASX",    "AUD"),
    Ticker("ANZ.AX",  "ANZ Group",                 "Financials",    "ASX",    "AUD"),
    Ticker("MQG.AX",  "Macquarie Group",           "Financials",    "ASX",    "AUD"),
    # ASX retail / consumer
    Ticker("WES.AX",  "Wesfarmers",                "Consumer",      "ASX",    "AUD"),
    Ticker("WOW.AX",  "Woolworths Group",          "Consumer",      "ASX",    "AUD"),
    Ticker("COL.AX",  "Coles Group",               "Consumer",      "ASX",    "AUD"),
    # ASX other large-cap
    Ticker("TLS.AX",  "Telstra",                   "Communications","ASX",    "AUD"),
    Ticker("CSL.AX",  "CSL Limited",               "Healthcare",    "ASX",    "AUD"),
    # US big-tech (proven pattern names)
    Ticker("MSFT",    "Microsoft",                 "Technology",    "NASDAQ", "USD"),
    Ticker("AAPL",    "Apple",                     "Technology",    "NASDAQ", "USD"),
    Ticker("AMZN",    "Amazon",                    "Consumer",      "NASDAQ", "USD"),
    Ticker("GOOGL",   "Alphabet (Google)",         "Communications","NASDAQ", "USD"),
    Ticker("NVDA",    "NVIDIA",                    "Technology",    "NASDAQ", "USD"),
    Ticker("META",    "Meta Platforms",            "Communications","NASDAQ", "USD"),
]


def by_symbol(symbol: str) -> Ticker | None:
    for t in WATCHLIST:
        if t.symbol == symbol:
            return t
    return None


def symbols() -> list[str]:
    return [t.symbol for t in WATCHLIST]


def asx_only() -> list[Ticker]:
    return [t for t in WATCHLIST if t.market == "ASX"]


def us_only() -> list[Ticker]:
    return [t for t in WATCHLIST if t.market in ("NASDAQ", "NYSE")]
