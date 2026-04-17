"""Classical technical indicators - all derived from price only.

Used as CONFIRMATION filters in the GO-signal decider, never as the
primary forecast. RSI, MACD, Bollinger Bands.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TechnicalSnapshot:
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bollinger_pct_b: float        # 0 = at lower band, 1 = at upper band
    bullish_confirmed: bool
    bearish_warning: bool
    notes: list[str]


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_mult: float = 2.0,
) -> pd.DataFrame:
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + std_mult * sd
    lower = ma - std_mult * sd
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame(
        {"middle": ma, "upper": upper, "lower": lower, "pct_b": pct_b}
    )


def snapshot(df: pd.DataFrame) -> TechnicalSnapshot:
    """Current-state snapshot used by the signal decider."""
    close = df["close"]
    if len(close) < 30:
        return TechnicalSnapshot(50, 0, 0, 0, 0.5, False, False, ["Insufficient data."])

    rsi_now = float(rsi(close).iloc[-1])
    macd_df = macd(close).iloc[-1]
    bb = bollinger_bands(close).iloc[-1]

    notes: list[str] = []
    bullish = True
    bearish = False

    if rsi_now > 70:
        notes.append(f"RSI {rsi_now:.0f} - overbought, due for a pullback.")
        bullish = False
        bearish = True
    elif rsi_now < 30:
        notes.append(f"RSI {rsi_now:.0f} - oversold, may be due for a bounce.")
    else:
        notes.append(f"RSI {rsi_now:.0f} - neutral zone.")

    if macd_df["histogram"] <= 0:
        notes.append("MACD histogram non-positive - momentum not confirming bullish.")
        bullish = False
    else:
        notes.append("MACD histogram positive - momentum confirming bullish.")

    pct_b = float(bb["pct_b"]) if pd.notna(bb["pct_b"]) else 0.5
    if pct_b > 0.95:
        notes.append("Price pinned to upper Bollinger band - extended.")
        bullish = False
        bearish = True
    elif pct_b < 0.05:
        notes.append("Price pinned to lower Bollinger band - capitulation territory.")

    return TechnicalSnapshot(
        rsi=rsi_now,
        macd=float(macd_df["macd"]),
        macd_signal=float(macd_df["signal"]),
        macd_histogram=float(macd_df["histogram"]),
        bollinger_pct_b=pct_b,
        bullish_confirmed=bullish,
        bearish_warning=bearish,
        notes=notes,
    )
