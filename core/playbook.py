"""Today's Playbook - the single-screen daily summary.

Boils a watchlist of analysis results down to three statements:

1. The single best opportunity right now (or "no good trades" if none).
2. The watchlist's overall mood (regime breakdown).
3. The next-up event to watch this week (e.g. an upcoming hold-window).

Pure functions over already-analysed dicts (the shape returned by
app_pipeline.analyse_one). No streamlit, no I/O, no fetching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PlaybookHeadline:
    title: str
    body: str
    accent: str   # "go" | "wait" | "avoid" | "info"


@dataclass(frozen=True)
class PlaybookMood:
    bull: int
    bear: int
    sideways: int
    total: int

    @property
    def dominant(self) -> str:
        counts = {"bull": self.bull, "bear": self.bear, "sideways": self.sideways}
        return max(counts, key=lambda k: counts[k])

    @property
    def description(self) -> str:
        if self.total == 0:
            return "No data yet"
        bull_pct = self.bull / self.total * 100
        bear_pct = self.bear / self.total * 100
        if bear_pct > 50:
            return (
                f"**Defensive mood.** {self.bear}/{self.total} stocks "
                f"({bear_pct:.0f}%) are in a bear regime. "
                "GO signals will be sparse - this is by design."
            )
        if bull_pct > 60:
            return (
                f"**Constructive mood.** {self.bull}/{self.total} stocks "
                f"({bull_pct:.0f}%) are in a bull regime. "
                "Good environment for GO signals."
            )
        return (
            f"**Mixed mood.** {self.bull} bull / {self.bear} bear / "
            f"{self.sideways} sideways out of {self.total}. "
            "Stock-by-stock reading required."
        )


@dataclass(frozen=True)
class PlaybookWatch:
    text: str
    symbol: str | None
    days_until: int | None


@dataclass(frozen=True)
class Playbook:
    headline: PlaybookHeadline
    mood: PlaybookMood
    watch: PlaybookWatch | None
    generated_at: datetime


def _best_go(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the highest-confidence GO signal across the watchlist."""
    gos = [r for r in rows if r.get("signal") == "GO"]
    if not gos:
        return None
    gos.sort(key=lambda r: r["signal_obj"].confidence, reverse=True)
    return gos[0]


def _runner_up(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """If no GO signals, surface the best WAIT — highest trust grade with positive expected return."""
    waits = [
        r for r in rows
        if r.get("signal") == "WAIT"
        and r.get("trust_grade") in ("A", "B")
        and r.get("expected_90d_pct", 0) > 0
        and "error" not in r
    ]
    if not waits:
        return None
    waits.sort(key=lambda r: (r["trust_score"], r["expected_90d_pct"]), reverse=True)
    return waits[0]


def _mood(rows: list[dict[str, Any]]) -> PlaybookMood:
    valid = [r for r in rows if "error" not in r and "regime" in r]
    bull = sum(1 for r in valid if r["regime"] == "bull")
    bear = sum(1 for r in valid if r["regime"] == "bear")
    sideways = sum(1 for r in valid if r["regime"] == "sideways")
    return PlaybookMood(bull=bull, bear=bear, sideways=sideways, total=len(valid))


def _next_watch(rows: list[dict[str, Any]]) -> PlaybookWatch | None:
    """Surface the most promising currently-active hold-window across the watchlist.

    Excludes stocks already showing a GO signal (those are in the headline).
    Ranks by score = avg return * hit rate.
    """
    candidates: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        if "error" in r or r.get("signal") == "GO":
            continue
        hold = r.get("hold")
        if hold is None:
            continue
        score = hold.avg_return_pct * (hold.hit_rate_pct / 100)
        if score > 0:
            candidates.append((score, r))
    if not candidates:
        return None
    candidates.sort(reverse=True, key=lambda x: x[0])
    _, row = candidates[0]
    hold = row["hold"]
    return PlaybookWatch(
        text=(
            f"**{row['symbol']}** ({row['name']}) is in a historically "
            f"favourable seasonal window: "
            f"avg gain {hold.avg_return_pct:+.1f}%, "
            f"hit rate {hold.hit_rate_pct:.0f}% "
            f"over {hold.n_years} years. "
            "Other GO conditions haven't lined up - watch closely."
        ),
        symbol=row["symbol"],
        days_until=None,
    )


def build(rows: list[dict[str, Any]]) -> Playbook:
    """Compose a full playbook from analysed-watchlist rows."""
    best = _best_go(rows)
    if best is not None:
        sig = best["signal_obj"]
        headline = PlaybookHeadline(
            title=f"GO: {best['symbol']} - {best['name']}",
            body=(
                f"{sig.headline} "
                f"Expected return {sig.expected_return_pct:+.1f}%, "
                f"confidence {sig.confidence:.0%}. "
                "See **Forward Outlook** for the full plan."
            ),
            accent="go",
        )
    else:
        runner = _runner_up(rows)
        if runner:
            headline = PlaybookHeadline(
                title="No GO signals - sit tight",
                body=(
                    f"Closest to firing: **{runner['symbol']}** "
                    f"({runner['name']}) - trust grade {runner['trust_grade']}, "
                    f"expected 90d move {runner['expected_90d_pct']:+.1f}%. "
                    "Not enough conditions agree yet."
                ),
                accent="wait",
            )
        else:
            headline = PlaybookHeadline(
                title="No GO signals - sit tight",
                body=(
                    "Nothing on the watchlist meets the GO criteria today. "
                    "This is the system being conservative. Check back in a few days."
                ),
                accent="wait",
            )
    return Playbook(
        headline=headline,
        mood=_mood(rows),
        watch=_next_watch(rows),
        generated_at=datetime.now(),
    )
