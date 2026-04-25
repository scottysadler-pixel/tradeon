"""Optional free-information headlines for speculation candidates.

This is intentionally a low-stakes add-on: the speculation scoring remains
forecast-first. News data is only used for optional context and a light sentiment
signal that can be shown in the UI.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

import yfinance as yf


POSITIVE = {
    "beats", "beat", "strong", "growth", "upgrade", "upgradeable", "upgraded",
    "profit", "profitability", "record", "demand", "increased", "expands",
    "win", "wins", "gains", "gain", "rally", "rallies", "buy", "outperform",
    "surpass", "surges", "breakthrough", "breaks", "expansion", "positive",
}
NEGATIVE = {
    "miss", "misses", "downgrade", "downgraded", "loss", "loses", "losses",
    "lawsuit", "probe", "warning", "drop", "decline", "declines", "sell",
    "default", "disappoint", "disappoints", "headwinds", "risk", "delay",
    "regulatory", "investigation", "fraud", "recall", "shut", "closure",
}


def _tokenise(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[a-zA-Z]+", text)]


def headline_sentiment(text: str) -> float:
    """Very lightweight polarity score in range [-1, 1]."""
    tokens = _tokenise(text)
    if not tokens:
        return 0.0
    pos = sum(1 for t in tokens if t in POSITIVE)
    neg = sum(1 for t in tokens if t in NEGATIVE)
    score = (pos - neg) / max(1, len(tokens))
    return max(-1.0, min(1.0, score * 8))


def _normalize_headline(raw: Any) -> dict[str, Any]:
    title = str(raw.get("title", "")).strip()
    if not title:
        return {}

    summary = str(raw.get("summary") or raw.get("content") or "").strip()
    published = raw.get("providerPublishTime") or raw.get("publishedDate") or raw.get("date")
    if isinstance(published, int):
        published_dt = datetime.fromtimestamp(published)
    elif isinstance(published, float):
        published_dt = datetime.fromtimestamp(int(published))
    elif isinstance(published, str):
        published_dt = _parse_published(published)
    else:
        published_dt = None

    return {
        "title": title,
        "summary": summary,
        "source": str(raw.get("provider", {}).get("name", "") or raw.get("publisher", "Unknown")),
        "url": str(raw.get("link", "") or raw.get("url", "")),
        "published_iso": published_dt.isoformat() if published_dt else "",
        "sentiment": headline_sentiment(f"{title} {summary}"),
    }


def _parse_published(raw: str) -> datetime | None:
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def fetch_headlines(symbol: str, max_items: int = 5, *, timeout_seconds: int = 8) -> list[dict[str, Any]]:
    """Fetch free news headlines through yfinance.

    If yfinance is unavailable or rate-limited, an empty list is returned and
    the speculation feature keeps working without headlines.
    """
    try:
        ticker = yf.Ticker(symbol)
        deadline = time.time() + timeout_seconds
        raw = ticker.news or []
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if time.time() > deadline:
            break
        normalized = _normalize_headline(item or {})
        if not normalized:
            continue
        title = normalized["title"].lower()
        if title in seen:
            continue
        seen.add(title)
        out.append(normalized)
        if len(out) >= max_items:
            break
    return out


def summarize_headlines(symbol: str, max_items: int = 5) -> dict[str, Any]:
    items = fetch_headlines(symbol, max_items=max_items)
    if not items:
        return {"available": False, "items": [], "avg_sentiment": 0.0, "label": "no_data"}

    avg = sum(item["sentiment"] for item in items) / len(items)
    if avg >= 0.2:
        label = "positive"
    elif avg <= -0.2:
        label = "negative"
    else:
        label = "neutral"
    return {
        "available": True,
        "items": items,
        "avg_sentiment": avg,
        "label": label,
    }

