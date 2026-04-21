"""Trade journal - log real trades and grade yourself.

Stores trades in a single CSV at <cache>/journal.csv. Each trade has a
`buy_*` set of fields (always required) and a `sell_*` set of fields
(empty until the trade is closed). Closing a trade is just calling
`close_trade()` with the closing date and price.

The journal is the user's personal data, NOT TRADEON's analysis output -
it's about whether YOU make money, not whether the model does. The
self-grade compares your real outcomes against (a) buy-and-hold and
(b) what TRADEON predicted at the time of entry.

Storage caveat for Streamlit Cloud: data_cache/ is ephemeral on the
free tier. Use the export/import buttons in the UI to keep a permanent
copy you control.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .costs import cgt_on_gain, round_trip_fees
from .data import CACHE_DIR

logger = logging.getLogger(__name__)

JOURNAL_PATH = CACHE_DIR / "journal.csv"

COLUMNS = [
    "trade_id",
    "ticker",
    "name",
    "market",
    "broker",
    "buy_date",
    "buy_price_aud",
    "shares",
    "tradeon_signal_at_entry",     # "GO" / "WAIT" / "AVOID" / "" (not consulted)
    "tradeon_predicted_pct",       # what TRADEON predicted at entry, if any
    "sell_date",                   # blank while open
    "sell_price_aud",              # blank while open
    "is_practice",                 # "True" for paper trades, "False" for real
    "notes",
]


@dataclass
class JournalEntry:
    trade_id: str
    ticker: str
    name: str
    market: str
    broker: str
    buy_date: date
    buy_price_aud: float
    shares: int
    tradeon_signal_at_entry: str = ""
    tradeon_predicted_pct: float | None = None
    sell_date: date | None = None
    sell_price_aud: float | None = None
    is_practice: bool = False
    notes: str = ""

    @property
    def is_open(self) -> bool:
        return self.sell_date is None

    @property
    def capital_aud(self) -> float:
        return self.buy_price_aud * self.shares

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "broker": self.broker,
            "buy_date": self.buy_date.isoformat(),
            "buy_price_aud": f"{self.buy_price_aud:.4f}",
            "shares": self.shares,
            "tradeon_signal_at_entry": self.tradeon_signal_at_entry,
            "tradeon_predicted_pct": (
                f"{self.tradeon_predicted_pct:.4f}"
                if self.tradeon_predicted_pct is not None else ""
            ),
            "sell_date": self.sell_date.isoformat() if self.sell_date else "",
            "sell_price_aud": (
                f"{self.sell_price_aud:.4f}" if self.sell_price_aud is not None else ""
            ),
            "is_practice": str(self.is_practice),
            "notes": self.notes,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "JournalEntry":
        def _opt_float(v: Any) -> float | None:
            if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)

        def _opt_date(v: Any) -> date | None:
            if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
                return None
            return datetime.fromisoformat(str(v)).date()

        def _parse_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            return s in ("true", "1", "yes")
        
        return cls(
            trade_id=str(row["trade_id"]),
            ticker=str(row["ticker"]),
            name=str(row.get("name", "")),
            market=str(row.get("market", "ASX")),
            broker=str(row.get("broker", "Stake")),
            buy_date=datetime.fromisoformat(str(row["buy_date"])).date(),
            buy_price_aud=float(row["buy_price_aud"]),
            shares=int(float(row["shares"])),
            tradeon_signal_at_entry=str(row.get("tradeon_signal_at_entry", "")),
            tradeon_predicted_pct=_opt_float(row.get("tradeon_predicted_pct")),
            sell_date=_opt_date(row.get("sell_date")),
            sell_price_aud=_opt_float(row.get("sell_price_aud")),
            is_practice=_parse_bool(row.get("is_practice", "False")),
            notes=str(row.get("notes", "")),
        )


def _ensure_header(path: Path) -> None:
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()


def load_journal(path: Path = JOURNAL_PATH) -> list[JournalEntry]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    return [JournalEntry.from_row(r) for _, r in df.iterrows()]


def save_journal(entries: list[JournalEntry], path: Path = JOURNAL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for e in entries:
            writer.writerow(e.to_row())


def add_entry(entry: JournalEntry, path: Path = JOURNAL_PATH) -> None:
    entries = load_journal(path)
    if any(e.trade_id == entry.trade_id for e in entries):
        raise ValueError(f"Duplicate trade_id: {entry.trade_id}")
    entries.append(entry)
    save_journal(entries, path)


def close_trade(
    trade_id: str,
    sell_date: date,
    sell_price_aud: float,
    *,
    notes_append: str = "",
    path: Path = JOURNAL_PATH,
) -> JournalEntry:
    entries = load_journal(path)
    target: JournalEntry | None = None
    for e in entries:
        if e.trade_id == trade_id:
            e.sell_date = sell_date
            e.sell_price_aud = sell_price_aud
            if notes_append:
                e.notes = (e.notes + " | " if e.notes else "") + notes_append
            target = e
            break
    if target is None:
        raise KeyError(f"No open trade with id {trade_id}")
    save_journal(entries, path)
    return target


def delete_entry(trade_id: str, path: Path = JOURNAL_PATH) -> bool:
    entries = load_journal(path)
    new = [e for e in entries if e.trade_id != trade_id]
    if len(new) == len(entries):
        return False
    save_journal(new, path)
    return True


def import_csv(raw_csv: str, path: Path = JOURNAL_PATH, *, replace: bool = False) -> int:
    """Import entries from a CSV string. Returns count imported.

    By default, merges (skips duplicate trade_ids). Pass replace=True to wipe first.
    """
    df = pd.read_csv(io.StringIO(raw_csv), dtype=str, keep_default_na=False)
    new_entries = [JournalEntry.from_row(r) for _, r in df.iterrows()]
    if replace:
        save_journal(new_entries, path)
        return len(new_entries)
    existing = load_journal(path)
    seen = {e.trade_id for e in existing}
    added = 0
    for ne in new_entries:
        if ne.trade_id not in seen:
            existing.append(ne)
            seen.add(ne.trade_id)
            added += 1
    save_journal(existing, path)
    return added


def export_csv(path: Path = JOURNAL_PATH) -> str:
    if not path.exists():
        return ",".join(COLUMNS) + "\n"
    return path.read_text(encoding="utf-8")


# ----- per-trade computed fields -----


@dataclass
class TradeOutcome:
    entry: JournalEntry
    gross_aud: float | None      # gross profit/loss in AUD before fees and tax
    fees_aud: float              # round-trip broker fees
    net_pre_tax_aud: float | None
    cgt_aud: float | None        # tax owed on gain
    net_after_tax_aud: float | None
    net_pct: float | None        # % return on invested capital, after everything
    days_held: int | None
    used_cgt_discount: bool      # held >= 365 days
    prediction_error_pct: float | None  # actual_pct - predicted_pct (None if no prediction)


def compute_outcome(
    entry: JournalEntry,
    *,
    marginal_tax_rate: float = 0.325,
) -> TradeOutcome:
    """Compute the financial outcome for a single trade entry.

    Returns dataclass with everything needed for display + summary stats.
    Open trades return None for sell-side fields.
    """
    fees = round_trip_fees(entry.capital_aud, entry.market, entry.broker)

    if entry.sell_date is None or entry.sell_price_aud is None:
        return TradeOutcome(
            entry=entry,
            gross_aud=None,
            fees_aud=fees,
            net_pre_tax_aud=None,
            cgt_aud=None,
            net_after_tax_aud=None,
            net_pct=None,
            days_held=None,
            used_cgt_discount=False,
            prediction_error_pct=None,
        )

    proceeds = entry.sell_price_aud * entry.shares
    gross = proceeds - entry.capital_aud
    net_pre_tax = gross - fees
    days = (entry.sell_date - entry.buy_date).days
    used_discount = days >= 365
    cgt = cgt_on_gain(net_pre_tax, held_days=days, marginal_rate=marginal_tax_rate)
    net_after_tax = net_pre_tax - cgt
    net_pct = (net_after_tax / entry.capital_aud) * 100 if entry.capital_aud else 0.0

    actual_pct = ((entry.sell_price_aud / entry.buy_price_aud) - 1) * 100
    pred_err = (
        actual_pct - entry.tradeon_predicted_pct
        if entry.tradeon_predicted_pct is not None
        else None
    )

    return TradeOutcome(
        entry=entry,
        gross_aud=gross,
        fees_aud=fees,
        net_pre_tax_aud=net_pre_tax,
        cgt_aud=cgt,
        net_after_tax_aud=net_after_tax,
        net_pct=net_pct,
        days_held=days,
        used_cgt_discount=used_discount,
        prediction_error_pct=pred_err,
    )


# ----- portfolio-level summary -----


@dataclass
class JournalSummary:
    total_trades: int
    open_trades: int
    closed_trades: int
    total_invested_aud: float
    realised_net_aud: float       # sum of net_after_tax across closed trades
    realised_pct: float           # weighted by invested capital
    hit_rate_pct: float           # % of closed trades that were profitable after tax
    average_days_held: float
    # vs TRADEON
    closed_with_predictions: int
    avg_prediction_error_pct: float | None  # mean of (actual - predicted) where both known
    direction_called_correctly_pct: float | None
    # the "did I beat the model" check
    trades_taken_against_wait: int
    against_wait_hit_rate_pct: float | None


def _safe_mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarise(entries: list[JournalEntry], *, marginal_tax_rate: float = 0.325) -> JournalSummary:
    outcomes = [compute_outcome(e, marginal_tax_rate=marginal_tax_rate) for e in entries]
    closed = [o for o in outcomes if o.net_after_tax_aud is not None]
    open_n = len(outcomes) - len(closed)

    total_invested = sum(e.capital_aud for e in entries)
    realised_net = sum(o.net_after_tax_aud for o in closed)  # type: ignore[misc]
    realised_pct = (
        sum(
            (o.net_after_tax_aud / o.entry.capital_aud) * 100  # type: ignore[operator]
            for o in closed if o.entry.capital_aud > 0
        ) / len(closed)
        if closed else 0.0
    )
    hit = sum(1 for o in closed if (o.net_after_tax_aud or 0) > 0)
    hit_rate = (hit / len(closed) * 100) if closed else 0.0
    avg_days = (
        sum(o.days_held or 0 for o in closed) / len(closed)
        if closed else 0.0
    )

    with_preds = [o for o in closed if o.prediction_error_pct is not None]
    avg_err = _safe_mean([o.prediction_error_pct for o in with_preds])  # type: ignore[misc]

    dir_correct = None
    if with_preds:
        n_correct = 0
        for o in with_preds:
            actual_pct = (
                ((o.entry.sell_price_aud / o.entry.buy_price_aud) - 1) * 100  # type: ignore[operator]
            )
            predicted = o.entry.tradeon_predicted_pct
            if predicted is None:
                continue
            if (actual_pct >= 0) == (predicted >= 0):
                n_correct += 1
        dir_correct = n_correct / len(with_preds) * 100

    against_wait = [
        o for o in closed
        if o.entry.tradeon_signal_at_entry in ("WAIT", "AVOID")
    ]
    against_wait_hit = (
        sum(1 for o in against_wait if (o.net_after_tax_aud or 0) > 0)
        / len(against_wait) * 100
    ) if against_wait else None

    return JournalSummary(
        total_trades=len(outcomes),
        open_trades=open_n,
        closed_trades=len(closed),
        total_invested_aud=total_invested,
        realised_net_aud=realised_net,
        realised_pct=realised_pct,
        hit_rate_pct=hit_rate,
        average_days_held=avg_days,
        closed_with_predictions=len(with_preds),
        avg_prediction_error_pct=avg_err,
        direction_called_correctly_pct=dir_correct,
        trades_taken_against_wait=len(against_wait),
        against_wait_hit_rate_pct=against_wait_hit,
    )


def next_trade_id() -> str:
    """Generate a fresh trade_id that doesn't collide with existing entries."""
    existing = {e.trade_id for e in load_journal()}
    n = len(existing) + 1
    while f"T{n:04d}" in existing:
        n += 1
    return f"T{n:04d}"


def generate_calendar_event(entry: JournalEntry, exit_date: date | None = None) -> str:
    """Generate an ICS calendar file for a trade exit reminder.
    
    Args:
        entry: The journal entry
        exit_date: Suggested exit date. If None, uses entry.sell_date or skips.
    
    Returns:
        ICS file content as a string
    """
    from datetime import timedelta
    
    # Determine exit date
    target_date = exit_date or entry.sell_date
    if not target_date:
        # No exit date known, can't create calendar event
        return ""
    
    # Create datetime objects (all-day event)
    dt_start = target_date
    dt_end = target_date + timedelta(days=1)
    
    # Format for ICS (YYYYMMDD)
    start_str = dt_start.strftime("%Y%m%d")
    end_str = dt_end.strftime("%Y%m%d")
    
    # Create reminder for 9 AM on the exit date
    alarm_time = target_date.strftime("%Y%m%d") + "T090000"
    
    # Build event details
    summary = f"TRADEON: Exit {entry.ticker}"
    practice_tag = " (PRACTICE)" if entry.is_practice else ""
    description = (
        f"Trade exit reminder{practice_tag}\\n"
        f"Ticker: {entry.ticker} ({entry.name})\\n"
        f"Entry: {entry.buy_date.isoformat()} @ A${entry.buy_price_aud:.2f}\\n"
        f"Shares: {entry.shares}\\n"
        f"Capital: A${entry.capital_aud:.2f}\\n"
        f"Trade ID: {entry.trade_id}\\n\\n"
        f"Action: Review position and consider exiting.\\n"
        f"Log exit in TRADEON Trade Journal."
    )
    
    # Generate ICS content
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TRADEON//Trade Journal//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{entry.trade_id}-{entry.buy_date.isoformat()}@tradeon.app
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTSTART;VALUE=DATE:{start_str}
DTEND;VALUE=DATE:{end_str}
SUMMARY:{summary}
DESCRIPTION:{description}
STATUS:CONFIRMED
SEQUENCE:0
BEGIN:VALARM
TRIGGER;VALUE=DATE-TIME:{alarm_time}
DESCRIPTION:Time to review {entry.ticker} exit
ACTION:DISPLAY
END:VALARM
END:VEVENT
END:VCALENDAR"""
    
    return ics_content
