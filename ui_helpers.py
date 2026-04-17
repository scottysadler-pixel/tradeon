"""Shared Streamlit UI helpers (formatting, badges, common widgets).

Allowed to import streamlit. core/ must NOT import this module.
"""

from __future__ import annotations

import streamlit as st

from core.glossary import explain
from core.tickers import WATCHLIST, Ticker, by_symbol


def page_setup(title: str, icon: str = "") -> None:
    st.set_page_config(
        page_title=f"{title} - TRADEON",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title(title)


def aud(amount: float | None) -> str:
    if amount is None:
        return "-"
    sign = "-" if amount < 0 else ""
    return f"{sign}A${abs(amount):,.2f}"


def pct(amount: float | None, decimals: int = 1) -> str:
    if amount is None:
        return "-"
    return f"{amount:+.{decimals}f}%"


def grade_badge(grade: str) -> str:
    color = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308",
             "D": "#f97316", "F": "#ef4444"}.get(grade, "#94a3b8")
    return (
        f"<span style='background:{color};padding:4px 10px;border-radius:8px;"
        f"font-weight:700;color:#0b1220'>{grade}</span>"
    )


def signal_badge(state: str) -> str:
    color = {"GO": "#22c55e", "WAIT": "#94a3b8", "AVOID": "#ef4444"}.get(state, "#94a3b8")
    return (
        f"<span style='background:{color};padding:4px 10px;border-radius:8px;"
        f"font-weight:700;color:#0b1220'>{state}</span>"
    )


def regime_badge(label: str) -> str:
    color = {"bull": "#22c55e", "bear": "#ef4444", "sideways": "#94a3b8"}.get(label, "#94a3b8")
    return (
        f"<span style='background:{color};padding:3px 8px;border-radius:6px;"
        f"font-weight:600;font-size:0.85em;color:#0b1220'>{label.upper()}</span>"
    )


def ticker_picker(default: str | None = None, key: str = "ticker_pick") -> Ticker:
    options = [t.symbol for t in WATCHLIST]
    labels = {t.symbol: t.display for t in WATCHLIST}
    default_index = options.index(default) if default in options else 0
    sym = st.selectbox(
        "Choose a stock",
        options,
        index=default_index,
        format_func=lambda s: labels.get(s, s),
        key=key,
    )
    return by_symbol(sym)  # type: ignore[return-value]


def broker_picker(key: str = "broker_pick") -> str:
    from core.costs import BROKERS
    options = list(BROKERS.keys())
    return st.sidebar.selectbox(
        "Your broker", options, index=options.index("Stake"), key=key,
        help="Used to model fees in backtests and trade walkthroughs.",
    )


def capital_input(default: float = 1000.0, key: str = "capital") -> float:
    return st.sidebar.number_input(
        "Capital per trade (AUD)",
        min_value=100.0,
        max_value=100_000.0,
        value=default,
        step=100.0,
        key=key,
        help="How much you'd typically commit per single position.",
    )


def metric_with_help(label: str, value: str, help_term: str | None = None, delta: str | None = None) -> None:
    st.metric(label, value, delta=delta, help=explain(help_term) if help_term else None)


def render_disclaimer() -> None:
    st.caption(
        "Decision support only - not financial advice. All projections are statistical "
        "estimates from raw historical price data. Past performance does not guarantee "
        "future results."
    )
