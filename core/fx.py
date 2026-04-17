"""AUD/USD currency conversion.

For US-listed stocks, the headline number a Sydney-based trader cares
about is the AUD return - which depends BOTH on the stock and on the
AUD/USD rate at the time of buy and sell. We pull historical FX rates
from yfinance (`AUDUSD=X`) and convert in-place.
"""

from __future__ import annotations

import logging

import pandas as pd

from .data import fetch_history
from .tickers import Ticker

logger = logging.getLogger(__name__)

FX_SYMBOL = "AUDUSD=X"  # 1 AUD = X USD


def fx_history(years: int = 25) -> pd.DataFrame:
    """Daily AUD/USD close history."""
    df = fetch_history(FX_SYMBOL, years=years, adjusted=False)
    return df[["date", "close"]].rename(columns={"close": "audusd"})


def to_aud(df_usd: pd.DataFrame) -> pd.DataFrame:
    """Convert a USD-denominated price frame into AUD using daily FX rates.

    Uses 1 AUD = X USD, so AUD price = USD price / AUDUSD.
    Forward-fills FX over weekends/holidays to align with stock trading days.
    """
    fx = fx_history()
    out = df_usd.copy()
    out["date"] = pd.to_datetime(out["date"])
    fx["date"] = pd.to_datetime(fx["date"])

    out = out.merge(fx, on="date", how="left")
    out["audusd"] = out["audusd"].ffill().bfill()

    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col] / out["audusd"]

    return out.drop(columns=["audusd"])


def normalise_to_aud(df: pd.DataFrame, ticker: Ticker) -> pd.DataFrame:
    """Return prices in AUD regardless of native currency."""
    if ticker.currency == "AUD":
        return df
    return to_aud(df)
