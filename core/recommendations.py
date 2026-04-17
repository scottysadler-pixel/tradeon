"""Suggest similar stocks worth adding to the watchlist.

Pure heuristic - we cannot 'discover' new tickers without external data,
so this works on the existing watchlist: rank already-known stocks not in
your active portfolio, by their recent pattern strength and recent trust
grade. Useful for surfacing 'this stock has been quietly excellent at
being predictable lately'.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tickers import Ticker, WATCHLIST


@dataclass
class Recommendation:
    ticker: Ticker
    pattern_strength: float
    trust_grade: str
    score: float
    reason: str


_GRADE_NUM = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


def rank(
    pattern_strength_by_symbol: dict[str, float],
    trust_grade_by_symbol: dict[str, str],
    *,
    exclude: list[str] | None = None,
    sector: str | None = None,
    top_n: int = 5,
) -> list[Recommendation]:
    """Return top-N watchlist candidates the user might want to focus on."""
    excl = set(exclude or [])
    recs: list[Recommendation] = []
    for t in WATCHLIST:
        if t.symbol in excl:
            continue
        if sector and t.sector != sector:
            continue
        ps = pattern_strength_by_symbol.get(t.symbol, 0.0)
        grade = trust_grade_by_symbol.get(t.symbol, "F")
        score = ps * 50 + _GRADE_NUM.get(grade, 1) * 10
        reason_bits = []
        if ps > 0.6:
            reason_bits.append("highly forecastable pattern")
        elif ps > 0.4:
            reason_bits.append("moderately forecastable")
        if grade in ("A", "B"):
            reason_bits.append(f"earned trust grade {grade}")
        reason = ", ".join(reason_bits) or "low conviction"
        recs.append(Recommendation(t, ps, grade, score, reason))
    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[:top_n]
