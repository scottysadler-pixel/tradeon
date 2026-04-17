"""Cross-asset macro confirmation (Enhancement #2).

A high-quality individual-stock signal can still get steamrolled by a hostile
overall market. This module asks two simple cross-asset questions:

  1. Is the parent index in a bear regime?
        ^GSPC for US tickers, ^AXJO for ASX
  2. Is volatility (^VIX) elevated?
        VIX > 25 = stress, > 30 = panic.

If either is hostile, we downgrade GO -> WAIT when the macro toggle is on.
This is the single biggest "free lunch" in equity timing - it costs nothing
to check and historically avoids the worst drawdown periods.

We re-use yfinance (already a dependency) and a 1h cache to keep things
cheap. If a fetch fails (offline / rate-limit), we return a "neutral"
mood that doesn't block any signals - "don't punish the user for an outage".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from .data import fetch_history
from .regime import detect_regime

logger = logging.getLogger(__name__)

MacroMood = Literal["favourable", "neutral", "hostile"]


@dataclass
class MacroSnapshot:
    mood: MacroMood
    index_symbol: str
    index_regime: str
    index_regime_confidence: float
    vix_level: float | None
    vix_state: str               # "calm", "elevated", "panic", "unknown"
    interpretation: str
    fetch_ok: bool


_CACHE: dict[str, tuple[datetime, MacroSnapshot]] = {}
_TTL = timedelta(hours=1)

_INDEX_FOR_MARKET = {
    "US":  "^GSPC",   # S&P 500
    "ASX": "^AXJO",   # ASX 200
}


def _classify_vix(level: float | None) -> str:
    if level is None:
        return "unknown"
    if level >= 30:
        return "panic"
    if level >= 25:
        return "elevated"
    return "calm"


def _fetch_vix_level() -> float | None:
    """Fetch most recent VIX close. Returns None on failure."""
    try:
        df = fetch_history("^VIX", years=1, adjusted=False)
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])
    except Exception as e:  # noqa: BLE001
        logger.warning("VIX fetch failed: %s", e)
        return None


def _fetch_index_regime(index_symbol: str) -> tuple[str, float, bool]:
    """Returns (regime_label, confidence, fetch_ok)."""
    try:
        df = fetch_history(index_symbol, years=10, adjusted=True)
        if df is None or len(df) < 252:
            return ("sideways", 0.0, False)
        rg = detect_regime(df)
        return (rg.label, rg.confidence, True)
    except Exception as e:  # noqa: BLE001
        logger.warning("Index %s fetch failed: %s", index_symbol, e)
        return ("sideways", 0.0, False)


def macro_snapshot(market: str = "US") -> MacroSnapshot:
    """Get the current macro mood for a market.

    Cached for 1 hour - macro mood doesn't change minute-to-minute.
    """
    cached = _CACHE.get(market)
    if cached and datetime.now() - cached[0] < _TTL:
        return cached[1]

    index_symbol = _INDEX_FOR_MARKET.get(market.upper(), "^GSPC")
    regime_label, regime_conf, fetch_ok = _fetch_index_regime(index_symbol)
    vix = _fetch_vix_level()
    vix_state = _classify_vix(vix)

    if regime_label == "bear" and regime_conf > 0.6:
        mood: MacroMood = "hostile"
        interp = (
            f"{index_symbol} is in a bear regime ({regime_conf:.0%} confidence). "
            "Single-stock GO signals are suppressed when the parent index is hostile."
        )
    elif vix_state == "panic":
        mood = "hostile"
        interp = (
            f"VIX = {vix:.1f} (panic). Even good single-stock setups get crushed in "
            "panic regimes - sitting out until VIX drops below 30."
        )
    elif vix_state == "elevated":
        mood = "neutral"
        interp = (
            f"VIX = {vix:.1f} (elevated). Index = {regime_label}. Conditions are "
            "mixed - single-stock GO signals require slightly higher conviction."
        )
    elif regime_label == "bull":
        mood = "favourable"
        vix_str = f"VIX = {vix:.1f}" if vix is not None else "VIX unavailable"
        interp = (
            f"{index_symbol} is in a bull regime ({regime_conf:.0%} confidence) "
            f"and {vix_str} (calm). Macro tailwind for single-stock GO signals."
        )
    else:
        mood = "neutral"
        vix_str = f"VIX = {vix:.1f}" if vix is not None else "VIX unavailable"
        interp = (
            f"{index_symbol} = {regime_label}, {vix_str}. No macro tailwind, "
            "but no major headwind either."
        )

    snap = MacroSnapshot(
        mood=mood,
        index_symbol=index_symbol,
        index_regime=regime_label,
        index_regime_confidence=regime_conf,
        vix_level=vix,
        vix_state=vix_state,
        interpretation=interp,
        fetch_ok=fetch_ok,
    )
    _CACHE[market] = (datetime.now(), snap)
    return snap


def macro_blocks_go(snap: MacroSnapshot) -> bool:
    """Should the macro toggle force a GO signal down to WAIT?"""
    return snap.mood == "hostile"


def clear_cache() -> None:
    """Useful for tests."""
    _CACHE.clear()
