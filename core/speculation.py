"""Paper prediction register for speculative ideas.

This module adds a manual register and outcome tracker for hypothetical
short/long predictions. It intentionally follows the same paper-trading spirit
as `core/journal.py` but stays separate so it can be iterated independently.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from typing import Optional
from uuid import uuid4

import pandas as pd

from .backtest import backtest_all, trust_grade
from .costs import cgt_on_gain, round_trip_fees
from .data import CACHE_DIR, fetch_history
from .forecast import ensemble_forecast, naive_forecast
from .fx import normalise_to_aud
from .tickers import WATCHLIST, by_symbol

Direction = Literal["LONG", "SHORT"]
PredictionStatus = Literal["open", "closed"]
PredictionGrade = Literal["A", "B", "C", "D", "F"]


@dataclass
class SpeculationCandidate:
    symbol: str
    name: str
    market: str
    expected_return_pct_30d: float
    expected_direction: Direction
    trust_grade: PredictionGrade
    trust_score: float
    confidence_score: float
    score_components: dict[str, float]
    score: float
    reasons: list[str]
    source_timestamp: str
    entry_price_aud: float
    projected_exit_price_aud: float
    news_score: float
    spot_aud: float
    naivedrift_pct: float
    notes: str


@dataclass
class SpeculationPrediction:
    prediction_id: str
    created_at: str
    symbol: str
    name: str
    market: str
    direction: Direction
    broker: str
    capital_aud: float
    horizon_days: int
    entry_price_aud: float
    expected_return_pct: float
    predicted_exit_date: str
    notes: str
    status: PredictionStatus = "open"
    close_date: str = ""
    close_price_aud: str = ""
    close_notes: str = ""

    @property
    def shares(self) -> int:
        if self.entry_price_aud <= 0:
            return 0
        return int(self.capital_aud // self.entry_price_aud)

    @property
    def invested_aud(self) -> float:
        return self.shares * self.entry_price_aud

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    def to_row(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "direction": self.direction,
            "broker": self.broker,
            "capital_aud": f"{self.capital_aud:.4f}",
            "horizon_days": str(self.horizon_days),
            "entry_price_aud": f"{self.entry_price_aud:.4f}",
            "expected_return_pct": f"{self.expected_return_pct:.4f}",
            "predicted_exit_date": self.predicted_exit_date,
            "notes": self.notes,
            "status": self.status,
            "close_date": self.close_date,
            "close_price_aud": self.close_price_aud,
            "close_notes": self.close_notes,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SpeculationPrediction":
        def _opt_float(v: Any) -> float:
            if v is None or v == "":
                return 0.0
            return float(v)

        return cls(
            prediction_id=str(row["prediction_id"]),
            created_at=str(row["created_at"]),
            symbol=str(row["symbol"]),
            name=str(row.get("name", "")),
            market=str(row.get("market", "ASX")),
            direction=cls._direction_from_text(str(row.get("direction", "LONG"))),
            broker=str(row.get("broker", "Stake")),
            capital_aud=float(row["capital_aud"]),
            horizon_days=int(float(row["horizon_days"])),
            entry_price_aud=_opt_float(row.get("entry_price_aud")),
            expected_return_pct=_opt_float(row.get("expected_return_pct")),
            predicted_exit_date=str(row.get("predicted_exit_date", "")),
            notes=str(row.get("notes", "")),
            status=str(row.get("status", "open")),  # type: ignore[assignment]
            close_date=str(row.get("close_date", "")),
            close_price_aud=str(row.get("close_price_aud", "")),
            close_notes=str(row.get("close_notes", "")),
        )

    @staticmethod
    def _direction_from_text(raw: str) -> Direction:
        value = raw.strip().upper()
        return "SHORT" if value == "SHORT" else "LONG"


@dataclass
class SpeculationOutcome:
    prediction_id: str
    direction: Direction
    predicted_return_pct: float
    actual_return_pct: float
    prediction_error_pct: float
    shares: int
    actual_days_held: int
    invested_aud: float
    gross_gain_aud: float
    fees_aud: float
    cgt_aud: float
    net_after_tax_aud: float
    net_pct: float
    direction_correct: bool


@dataclass
class CandidateBundle:
    generated_at: str
    horizon_days: int
    scanned_count: int
    long: list[SpeculationCandidate]
    short: list[SpeculationCandidate]
    notes: list[str] = field(default_factory=list)


@dataclass
class SpeculationSummary:
    total_predictions: int
    open_count: int
    closed_count: int
    realized_net_aud: float
    realized_pct: float
    hit_rate_pct: float
    avg_actual_return_pct: float | None
    avg_pred_error_pct: float | None
    avg_days_held: float


SPECULATION_PATH = CACHE_DIR / "speculation_register.csv"
COLUMNS = [
    "prediction_id",
    "created_at",
    "symbol",
    "name",
    "market",
    "direction",
    "broker",
    "capital_aud",
    "horizon_days",
    "entry_price_aud",
    "expected_return_pct",
    "predicted_exit_date",
    "notes",
    "status",
    "close_date",
    "close_price_aud",
    "close_notes",
]

DEFAULT_MIN_SCORE = 0.18


def _score_grade(grade: PredictionGrade) -> float:
    return {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.25, "F": 0.05}.get(grade, 0.2)


def _clamp01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def next_prediction_id() -> str:
    return f"S-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


def _to_aud_data(symbol: str) -> pd.DataFrame:
    raw = fetch_history(symbol, years=20, adjusted=True)
    t = by_symbol(symbol)
    if t is None:
        return raw
    return normalise_to_aud(raw, t)


def build_speculation_candidates(
    *,
    broker: str = "Stake",
    horizon_days: int = 30,
    max_symbols: int | None = 8,
    include_news: bool = False,
    min_score: float = DEFAULT_MIN_SCORE,
    skip_low_grade: bool = True,
) -> CandidateBundle:
    selected = WATCHLIST[:max_symbols] if isinstance(max_symbols, int) else WATCHLIST
    candidates: list[SpeculationCandidate] = []
    skipped: list[str] = []

    for t in selected:
        try:
            df = _to_aud_data(t.symbol)
        except Exception as exc:
            skipped.append(f"{t.symbol}: {exc}")
            continue
        if len(df) < 252 * 2:
            skipped.append(f"{t.symbol}: insufficient data")
            continue

        bt = backtest_all(df, horizon_days=horizon_days, market=t.market, broker=broker)
        grade = trust_grade(bt)
        if skip_low_grade and grade.grade == "F":
            skipped.append(f"{t.symbol}: trust grade F")
            continue

        f = ensemble_forecast(df, horizon_days)
        n = naive_forecast(df, horizon_days)
        spot = float(df["close"].iloc[-1])
        projected = float(f.forecast_mean[-1])
        naive_end = float(n.forecast_mean[-1])
        expected_pct = ((projected / spot) - 1) * 100
        if abs(expected_pct) < 0.5:
            skipped.append(f"{t.symbol}: tiny predicted drift")
            continue

        expected_dir = "LONG" if expected_pct >= 0 else "SHORT"
        news_score = 0.0
        reasons = [
            f"Trust {grade.grade} (score {grade.score:.0f}/100)",
            f"Expected {expected_pct:+.1f}% in {horizon_days} days",
            f"30d naive drift {((naive_end / spot) - 1) * 100:+.1f}%",
        ]
        if include_news:
            try:
                from .speculation_news import summarize_headlines

                news_ctx = summarize_headlines(t.symbol, max_items=4)
                news_score = float(news_ctx.get("avg_sentiment", 0.0))
                if news_score != 0.0:
                    reasons.append(f"News sentiment: {news_ctx.get('label', 'neutral')}")
            except Exception:
                news_score = 0.0
            if news_score != 0.0:
                reasons.append(
                    f"News score {(news_score + 1.0) / 2.0:.2f}"
                )
        score_components = {
            "trust": _score_grade(grade.grade),
            "directional": _clamp01((bt["ensemble"].directional_accuracy_pct - 40.0) / 60.0),
            "magnitude": _clamp01(abs(expected_pct) / 12.0),
            "naive_lift": _clamp01((bt["ensemble"].directional_accuracy_pct - bt["naive"].directional_accuracy_pct + 30.0) / 60.0),
            "news": _clamp01((news_score + 1.0) / 2.0 if include_news else 0.0),
        }
        score = (
            0.40 * score_components["trust"]
            + 0.25 * score_components["directional"]
            + 0.20 * score_components["magnitude"]
            + 0.10 * score_components["naive_lift"]
            + 0.05 * score_components["news"]
        )
        if include_news:
            reasons.append(
                "Optional media context enabled (lightweight only; not a replacement for model output)"
            )

        candidates.append(
            SpeculationCandidate(
                symbol=t.symbol,
                name=t.name,
                market=t.market,
                expected_return_pct_30d=expected_pct,
                expected_direction=expected_dir,
                trust_grade=grade.grade,
                trust_score=score_components["trust"],
                confidence_score=score,
                score_components=score_components,
                score=score,
                reasons=reasons,
                source_timestamp=datetime.utcnow().isoformat(),
                entry_price_aud=spot,
                projected_exit_price_aud=projected,
                news_score=(news_score or 0.0),
                spot_aud=spot,
                naivedrift_pct=((naive_end / spot) - 1) * 100,
                notes=" | ".join(reasons),
            )
        )

    long = sorted(
        [c for c in candidates if c.expected_direction == "LONG"],
        key=lambda c: c.score,
        reverse=True,
    )
    short = sorted(
        [c for c in candidates if c.expected_direction == "SHORT"],
        key=lambda c: c.score,
        reverse=True,
    )
    long = [c for c in long if c.score >= min_score][:10]
    short = [c for c in short if c.score >= min_score][:10]

    return CandidateBundle(
        generated_at=datetime.utcnow().isoformat(),
        horizon_days=horizon_days,
        scanned_count=len(selected),
        long=long,
        short=short,
        notes=skipped,
    )


def _ensure_header(path: Optional[Path] = None) -> None:
    if path is None:
        path = SPECULATION_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()


def load_register(path: Optional[Path] = None) -> list[SpeculationPrediction]:
    if path is None:
        path = SPECULATION_PATH
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    return [SpeculationPrediction.from_row(r) for _, r in df.iterrows()]


def save_register(entries: list[SpeculationPrediction], path: Optional[Path] = None) -> None:
    if path is None:
        path = SPECULATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for e in entries:
            writer.writerow(e.to_row())


def add_prediction(entry: SpeculationPrediction, path: Optional[Path] = None) -> None:
    if path is None:
        path = SPECULATION_PATH
    _ensure_header(path)
    entries = load_register(path)
    if any(e.prediction_id == entry.prediction_id for e in entries):
        raise ValueError(f"Duplicate prediction id: {entry.prediction_id}")
    entries.append(entry)
    save_register(entries, path)


def close_prediction(
    prediction_id: str,
    close_date: date,
    close_price_aud: float,
    path: Optional[Path] = None,
    *,
    notes: str = "",
) -> tuple[SpeculationPrediction, SpeculationOutcome]:
    if path is None:
        path = SPECULATION_PATH
    entries = load_register(path)
    target: SpeculationPrediction | None = None
    for e in entries:
        if e.prediction_id == prediction_id:
            if not e.is_open:
                raise ValueError(f"Prediction already closed: {prediction_id}")
            e.status = "closed"
            e.close_date = close_date.isoformat()
            e.close_price_aud = f"{close_price_aud:.4f}"
            if notes:
                e.close_notes = notes
            target = e
            break
    if target is None:
        raise KeyError(f"No open prediction with id {prediction_id}")

    outcome = compute_outcome(target, close_date=close_date, close_price_aud=close_price_aud)
    save_register(entries, path)
    return target, outcome


def delete_prediction(prediction_id: str, path: Optional[Path] = None) -> bool:
    if path is None:
        path = SPECULATION_PATH
    entries = load_register(path)
    kept = [e for e in entries if e.prediction_id != prediction_id]
    if len(kept) == len(entries):
        return False
    save_register(kept, path)
    return True


def _safe_float(value: Any) -> float:
    if value is None or value == "" or (isinstance(value, str) and value.upper() in ("NONE", "NA", "N/A")):
        return 0.0
    if isinstance(value, str) and value.replace(".", "", 1).replace("-", "", 1).replace("+", "", 1).replace("e", "", 1).replace("E", "", 1).isdigit():
        return float(value)
    return float(value)


def compute_outcome(
    entry: SpeculationPrediction,
    *,
    close_date: date,
    close_price_aud: float | None = None,
    include_tax: bool = True,
    marginal_tax_rate: float = 0.325,
) -> SpeculationOutcome:
    if close_price_aud is None:
        if not entry.close_price_aud:
            raise ValueError(f"Prediction {entry.prediction_id} missing close price")
        close_price_aud = _safe_float(entry.close_price_aud)

    if entry.shares <= 0:
        return SpeculationOutcome(
            prediction_id=entry.prediction_id,
            direction=entry.direction,
            predicted_return_pct=entry.expected_return_pct,
            actual_return_pct=0.0,
            prediction_error_pct=-entry.expected_return_pct,
            shares=0,
            actual_days_held=0,
            invested_aud=0.0,
            gross_gain_aud=0.0,
            fees_aud=0.0,
            cgt_aud=0.0,
            net_after_tax_aud=0.0,
            net_pct=0.0,
            direction_correct=False,
        )

    direction_mult = 1 if entry.direction == "LONG" else -1
    actual_return_decimal = ((close_price_aud / entry.entry_price_aud) - 1.0) * direction_mult
    actual_return_pct = actual_return_decimal * 100
    invested = entry.invested_aud
    gross_gain = invested * actual_return_decimal
    fees = round_trip_fees(invested, entry.market, entry.broker)
    net_after_fees = gross_gain - fees
    held_days = (close_date - datetime.fromisoformat(entry.created_at).date()).days
    cgt = cgt_on_gain(net_after_fees, held_days, marginal_rate=marginal_tax_rate) if include_tax else 0.0
    net_after_tax = net_after_fees - cgt
    net_pct = (net_after_tax / entry.capital_aud) * 100 if entry.capital_aud else 0.0

    prediction_error_pct = actual_return_pct - entry.expected_return_pct
    direction_correct = (entry.expected_return_pct >= 0 and actual_return_pct >= 0) or (
        entry.expected_return_pct < 0 and actual_return_pct < 0
    )

    return SpeculationOutcome(
        prediction_id=entry.prediction_id,
        direction=entry.direction,
        predicted_return_pct=entry.expected_return_pct,
        actual_return_pct=actual_return_pct,
        prediction_error_pct=prediction_error_pct,
        shares=entry.shares,
        actual_days_held=held_days,
        invested_aud=invested,
        gross_gain_aud=gross_gain,
        fees_aud=fees,
        cgt_aud=cgt,
        net_after_tax_aud=net_after_tax,
        net_pct=net_pct,
        direction_correct=direction_correct,
    )


def summarise(entries: list[SpeculationPrediction]) -> SpeculationSummary:
    open_count = sum(1 for e in entries if e.is_open)
    closed_entries = [e for e in entries if not e.is_open]
    if not closed_entries:
        return SpeculationSummary(
            total_predictions=len(entries),
            open_count=open_count,
            closed_count=0,
            realized_net_aud=0.0,
            realized_pct=0.0,
            hit_rate_pct=0.0,
            avg_actual_return_pct=None,
            avg_pred_error_pct=None,
            avg_days_held=0.0,
        )

    outcomes: list[SpeculationOutcome] = []
    for e in closed_entries:
        if not e.close_date:
            continue
        outcomes.append(
            compute_outcome(
                e,
                close_date=datetime.fromisoformat(e.close_date).date(),
                close_price_aud=float(e.close_price_aud),
            )
        )

    if not outcomes:
        return SpeculationSummary(
            total_predictions=len(entries),
            open_count=open_count,
            closed_count=0,
            realized_net_aud=0.0,
            realized_pct=0.0,
            hit_rate_pct=0.0,
            avg_actual_return_pct=None,
            avg_pred_error_pct=None,
            avg_days_held=0.0,
        )

    realised_net = sum(o.net_after_tax_aud for o in outcomes)
    total_invested = sum(o.invested_aud for o in outcomes)
    realised_pct = (realised_net / total_invested) * 100 if total_invested else 0.0
    hit_rate = (sum(1 for o in outcomes if o.actual_return_pct > 0) / len(outcomes)) * 100
    avg_actual = sum(o.actual_return_pct for o in outcomes) / len(outcomes)
    avg_error = sum(o.prediction_error_pct for o in outcomes) / len(outcomes)
    avg_days = sum(o.actual_days_held for o in outcomes) / len(outcomes)

    return SpeculationSummary(
        total_predictions=len(entries),
        open_count=open_count,
        closed_count=len(outcomes),
        realized_net_aud=realised_net,
        realized_pct=realised_pct,
        hit_rate_pct=hit_rate,
        avg_actual_return_pct=avg_actual,
        avg_pred_error_pct=avg_error,
        avg_days_held=avg_days,
    )

