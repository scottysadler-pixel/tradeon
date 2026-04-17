"""Smoke tests for the Tier 1 features: playbook, journal, broker links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.broker_links import broker_link, confirmation_checklist, order_ticket, yahoo_chart_url
from core.journal import (
    JournalEntry,
    add_entry,
    close_trade,
    compute_outcome,
    delete_entry,
    export_csv,
    import_csv,
    load_journal,
    next_trade_id,
    save_journal,
    summarise,
)
from core.playbook import build, _best_go, _mood, _next_watch
from core.tickers import by_symbol


# ----- Broker links -----

def test_yahoo_chart_url_format():
    t = by_symbol("MSFT")
    assert yahoo_chart_url(t) == "https://finance.yahoo.com/quote/MSFT"
    bhp = by_symbol("BHP.AX")
    assert yahoo_chart_url(bhp) == "https://finance.yahoo.com/quote/BHP.AX"


def test_broker_link_for_known_brokers():
    t = by_symbol("MSFT")
    for broker in ["CommSec", "Stake", "Pearler", "SelfWealth"]:
        link = broker_link(broker, t)
        assert link.url.startswith("https://")
        assert broker in link.label
        assert "MSFT" in link.note


def test_order_ticket_well_formed():
    @dataclass
    class FakeSig:
        suggested_entry_price: float = 100.0
        suggested_stop_price: float = 95.0
        suggested_exit_date: date = date(2026, 7, 15)

    t = by_symbol("MSFT")
    ticket = order_ticket(FakeSig(), t, shares=10, spot_price_aud=100.0)
    assert "LIMIT BUY" in ticket
    assert "10 x MSFT" in ticket
    assert "stop @" in ticket
    assert "2026-07-15" in ticket


def test_confirmation_checklist_includes_symbol():
    @dataclass
    class FakeSig:
        suggested_entry_price: float = 100.0
        suggested_stop_price: float = 95.0
        suggested_exit_date: date = date(2026, 7, 15)

    t = by_symbol("BHP.AX")
    checks = confirmation_checklist(FakeSig(), t)
    assert any("BHP.AX" in c for c in checks)
    assert any("LIMIT" in c for c in checks)


# ----- Playbook -----

@dataclass
class FakeSignalObj:
    headline: str
    confidence: float
    expected_return_pct: float


@dataclass
class FakeHold:
    avg_return_pct: float
    hit_rate_pct: float
    n_years: int


def _make_row(symbol, name, signal, trust_grade="B", trust_score=70,
              regime="bull", expected_pct=2.0, hold=None, conf=0.7):
    return {
        "symbol": symbol, "name": name, "signal": signal,
        "trust_grade": trust_grade, "trust_score": trust_score,
        "regime": regime, "expected_90d_pct": expected_pct,
        "signal_obj": FakeSignalObj(
            headline=f"{symbol} headline", confidence=conf,
            expected_return_pct=expected_pct,
        ),
        "hold": hold,
    }


def test_playbook_picks_highest_confidence_go():
    rows = [
        _make_row("AAA", "Alpha", "GO", conf=0.6, expected_pct=3.0),
        _make_row("BBB", "Beta", "GO", conf=0.9, expected_pct=8.0),
        _make_row("CCC", "Gamma", "WAIT"),
    ]
    pb = build(rows)
    assert "BBB" in pb.headline.title
    assert pb.headline.accent == "go"


def test_playbook_falls_back_to_runner_up_when_no_gos():
    rows = [
        _make_row("AAA", "Alpha", "WAIT", trust_grade="A", expected_pct=4.0),
        _make_row("BBB", "Beta", "WAIT", trust_grade="C", expected_pct=6.0),  # excluded - C grade
        _make_row("CCC", "Gamma", "AVOID"),
    ]
    pb = build(rows)
    assert pb.headline.accent == "wait"
    assert "AAA" in pb.headline.body  # only A/B grades surface as runner-up


def test_playbook_handles_empty_watchlist():
    pb = build([])
    assert pb.headline.accent == "wait"
    assert pb.mood.total == 0


def test_playbook_mood_classifies_bear_correctly():
    rows = [_make_row(f"S{i}", f"S{i}", "WAIT", regime="bear") for i in range(7)]
    rows += [_make_row(f"B{i}", f"B{i}", "WAIT", regime="bull") for i in range(3)]
    pb = build(rows)
    assert pb.mood.bear == 7
    assert "Defensive" in pb.mood.description


def test_playbook_watch_excludes_go_signals():
    hot_hold = FakeHold(avg_return_pct=5.0, hit_rate_pct=80, n_years=15)
    rows = [
        _make_row("GO1", "GoStock", "GO", hold=hot_hold, conf=0.9),
        _make_row("WAT", "WaitStock", "WAIT", hold=hot_hold),
    ]
    pb = build(rows)
    assert pb.watch is not None
    assert pb.watch.symbol == "WAT"


# ----- Journal -----

def test_journal_round_trip(tmp_path):
    """Add -> save -> load cycle preserves data."""
    p = tmp_path / "j.csv"
    e = JournalEntry(
        trade_id="T0001", ticker="MSFT", name="Microsoft",
        market="NASDAQ", broker="Stake",
        buy_date=date(2026, 1, 5), buy_price_aud=600.0, shares=2,
        tradeon_signal_at_entry="GO", tradeon_predicted_pct=5.0,
    )
    save_journal([e], path=p)
    loaded = load_journal(path=p)
    assert len(loaded) == 1
    assert loaded[0].trade_id == "T0001"
    assert loaded[0].buy_price_aud == 600.0
    assert loaded[0].shares == 2
    assert loaded[0].is_open


def test_journal_close_trade_computes_outcome(tmp_path, monkeypatch):
    p = tmp_path / "j.csv"
    monkeypatch.setattr("core.journal.JOURNAL_PATH", p)
    e = JournalEntry(
        trade_id="T0001", ticker="MSFT", name="Microsoft",
        market="NASDAQ", broker="Stake",
        buy_date=date(2025, 1, 5), buy_price_aud=600.0, shares=2,
        tradeon_signal_at_entry="GO", tradeon_predicted_pct=5.0,
    )
    add_entry(e, path=p)
    closed = close_trade("T0001", date(2025, 4, 5), 660.0, path=p)
    assert closed.sell_price_aud == 660.0
    out = compute_outcome(closed)
    assert out.gross_aud == (660.0 - 600.0) * 2
    assert out.fees_aud > 0
    assert out.days_held == 90
    assert not out.used_cgt_discount  # under 365 days
    assert out.prediction_error_pct == ((660 / 600 - 1) * 100) - 5.0


def test_journal_summary_metrics(tmp_path):
    p = tmp_path / "j.csv"
    entries = [
        JournalEntry(
            trade_id="T0001", ticker="MSFT", name="Microsoft",
            market="NASDAQ", broker="Stake",
            buy_date=date(2025, 1, 5), buy_price_aud=600.0, shares=2,
            tradeon_signal_at_entry="GO", tradeon_predicted_pct=5.0,
            sell_date=date(2025, 4, 5), sell_price_aud=660.0,  # +10% gain
        ),
        JournalEntry(
            trade_id="T0002", ticker="BHP.AX", name="BHP",
            market="ASX", broker="Stake",
            buy_date=date(2025, 2, 1), buy_price_aud=40.0, shares=25,
            tradeon_signal_at_entry="WAIT",  # against the signal
            sell_date=date(2025, 5, 1), sell_price_aud=38.0,  # -5% loss
        ),
        JournalEntry(  # open trade
            trade_id="T0003", ticker="WES.AX", name="Wesfarmers",
            market="ASX", broker="Stake",
            buy_date=date(2026, 4, 1), buy_price_aud=70.0, shares=10,
        ),
    ]
    save_journal(entries, path=p)
    loaded = load_journal(path=p)
    summ = summarise(loaded)
    assert summ.total_trades == 3
    assert summ.open_trades == 1
    assert summ.closed_trades == 2
    assert summ.hit_rate_pct == 50.0  # 1 of 2 closed was profitable after tax
    assert summ.trades_taken_against_wait == 1
    assert summ.against_wait_hit_rate_pct == 0.0  # the WAIT-defied trade lost


def test_journal_csv_export_import_round_trip(tmp_path):
    p = tmp_path / "j.csv"
    e = JournalEntry(
        trade_id="T0001", ticker="MSFT", name="Microsoft",
        market="NASDAQ", broker="Stake",
        buy_date=date(2026, 1, 5), buy_price_aud=600.0, shares=2,
    )
    save_journal([e], path=p)
    raw = export_csv(path=p)
    p2 = tmp_path / "j2.csv"
    n = import_csv(raw, path=p2, replace=True)
    assert n == 1
    assert load_journal(path=p2)[0].trade_id == "T0001"


def test_journal_delete_entry(tmp_path):
    p = tmp_path / "j.csv"
    e1 = JournalEntry(
        trade_id="T0001", ticker="MSFT", name="Microsoft",
        market="NASDAQ", broker="Stake",
        buy_date=date(2026, 1, 5), buy_price_aud=600.0, shares=2,
    )
    e2 = JournalEntry(
        trade_id="T0002", ticker="BHP.AX", name="BHP",
        market="ASX", broker="Stake",
        buy_date=date(2026, 2, 1), buy_price_aud=40.0, shares=25,
    )
    save_journal([e1, e2], path=p)
    assert delete_entry("T0001", path=p) is True
    remaining = load_journal(path=p)
    assert len(remaining) == 1
    assert remaining[0].trade_id == "T0002"
