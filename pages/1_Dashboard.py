"""Dashboard - watchlist overview with trust grades and signal status.

Heavy computation per stock is cached for an hour so flipping between
pages is snappy. First load takes a while because we backtest every
watchlist stock.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pipeline import analyse_one, mark_watchlist_warm
from core.analysis import stock_stats
from core.settings import from_session as enh_from_session
from core.tickers import WATCHLIST
from ui_helpers import (
    grade_badge,
    page_setup,
    pct,
    regime_badge,
    render_disclaimer,
    signal_badge,
)

page_setup("Dashboard")
broker = st.session_state.get("broker", "Stake")
enh = enh_from_session(st.session_state)


@st.cache_data(ttl=3600, show_spinner=False)
def _enrich_with_stats(
    symbol: str,
    broker: str,
    enh_label: str,
    enh_garch: bool,
    enh_macro: bool,
    enh_regime_grade: bool,
    enh_recency_weighted: bool,
    enh_drawdown_breaker: bool,
) -> dict:
    """analyse_one() result enriched with descriptive stats for the table."""
    base = analyse_one(
        symbol, broker=broker,
        enh_label=enh_label, enh_garch=enh_garch,
        enh_macro=enh_macro, enh_regime_grade=enh_regime_grade,
        enh_recency_weighted=enh_recency_weighted,
        enh_drawdown_breaker=enh_drawdown_breaker,
    )
    if "error" in base:
        return base
    stats = stock_stats(base["df"])
    return {
        **{k: v for k, v in base.items() if k != "df" and not k.endswith("_obj")},
        "pattern_strength": stats.pattern_strength,
        "cagr_pct": stats.cagr_pct,
        "vol_pct": stats.annualised_vol_pct,
        "max_dd_pct": stats.max_drawdown_pct,
    }


st.markdown(
    "Watchlist overview. **Default state is WAIT** - GO signals only appear when "
    "multiple indicators agree. Most days you'll see mostly grey. That's the system "
    "working correctly."
)

col_run, col_refresh = st.columns([3, 1])
with col_run:
    st.caption(
        f"Analysing **{len(WATCHLIST)} stocks** - first load takes a few minutes "
        "while we backtest every name. Subsequent loads are instant (cached 1hr)."
    )
with col_refresh:
    if st.button("Refresh all"):
        st.cache_data.clear()
        st.rerun()

progress = st.progress(0.0, text="Crunching...")
rows: list[dict] = []
errors: list[str] = []

for i, t in enumerate(WATCHLIST):
    progress.progress((i + 1) / len(WATCHLIST), text=f"Analysing {t.symbol}...")
    try:
        rows.append(_enrich_with_stats(
            t.symbol, broker,
            getattr(enh, "short_label", lambda: "vanilla")(),
            bool(getattr(enh, "use_garch", False)),
            bool(getattr(enh, "use_macro_confirm", False)),
            bool(getattr(enh, "use_regime_grade", False)),
            bool(getattr(enh, "use_recency_weighted", False)),
            bool(getattr(enh, "use_drawdown_breaker", False)),
        ))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{t.symbol}: {e}")
progress.empty()
mark_watchlist_warm(broker, enh)

if enh.any_active():
    st.info(f"Active enhancements: **{enh.short_label()}** - results below reflect these toggles. Adjust in Strategy Lab.")

if errors:
    with st.expander(f"{len(errors)} symbol(s) failed to load"):
        for line in errors:
            st.warning(line)

ok_rows = [r for r in rows if "error" not in r]
df_summary = pd.DataFrame(ok_rows)

if df_summary.empty:
    st.error("No data loaded. Check internet connection and try Refresh.")
    st.stop()

# Headline counts
go_n = (df_summary["signal"] == "GO").sum()
wait_n = (df_summary["signal"] == "WAIT").sum()
avoid_n = (df_summary["signal"] == "AVOID").sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "GO signals",
    int(go_n),
    help=(
        "Stocks where every condition lined up: trust grade A or B, regime "
        "is bull/sideways, an active hold-window matches, forecast lift is "
        "materially positive, a technical confirms, and no earnings window "
        "is active. **Most days this is 0** — that's the point."
    ),
)
m2.metric(
    "WAIT",
    int(wait_n),
    help=(
        "The default state. At least one condition isn't lined up right "
        "now. The system is staying out. Open the **Forward Outlook** page "
        "to see only the GOs; come back to the Dashboard for the full picture."
    ),
)
m3.metric(
    "AVOID",
    int(avoid_n),
    help=(
        "A stronger 'no' than WAIT. The trust grade is poor (D or F) AND "
        "the regime is bear. The system is explicitly recommending you "
        "don't trust its forecast on this stock right now."
    ),
)
m4.metric(
    "Stocks analysed",
    len(df_summary),
    help=(
        f"Out of {len(WATCHLIST)} stocks in the watchlist, this many "
        "completed the full pipeline successfully. Edit `core/tickers.py` "
        "to add or remove stocks."
    ),
)

with st.expander("How to read this table", expanded=False):
    st.markdown(
        """
**Each card has 5 columns:**

| Column | What you're looking at |
|---|---|
| **Symbol + name** | The ticker, sector, and market. ASX names end in `.AX`. |
| **Trust** | A-F grade for how well our forecasts have matched reality on THIS stock historically, net of fees + tax. The 0-100 score below is the underlying number (A ≥ 80, B 65-79, C 50-64). |
| **Regime** | Current market mood for this stock: bull / bear / sideways. The pattern number below (0-1) is how seasonally repeatable the stock is — higher = more predictable. |
| **Signal** | GO / WAIT / AVOID. The % below is the expected 90-day net AUD return. A negative % is a warning, not a typo. |
| **Headline** | One-line summary of the verdict. The hold-window caption tells you the historically best buy-month / sell-month combo for this stock. |

**Sort tip:** the table is already sorted by signal (GO at top), then by trust score. Look at the GOs first.

**Cross-reference:** click any stock you want to dig into in the **Deep Dive** page — that gives you the full 20-year report behind a row.
        """
    )

st.markdown("### Watchlist")

display = df_summary.sort_values(
    by=["signal", "trust_score"],
    key=lambda c: c.map({"GO": 0, "WAIT": 1, "AVOID": 2}) if c.name == "signal" else c,
    ascending=[True, False],
).reset_index(drop=True)

# Render the table manually with HTML badges for trust grade and signal
for _, r in display.iterrows():
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 3])
        with c1:
            st.markdown(f"**{r['symbol']}** - {r['name']}")
            st.caption(f"{r['sector']} | {r['market']}")
        with c2:
            st.markdown(f"Trust: {grade_badge(r['trust_grade'])}", unsafe_allow_html=True)
            st.caption(f"Score {r['trust_score']:.0f}/100")
        with c3:
            st.markdown(f"Regime: {regime_badge(r['regime'])}", unsafe_allow_html=True)
            st.caption(f"Pattern {r['pattern_strength']:.2f}")
        with c4:
            st.markdown(f"Signal: {signal_badge(r['signal'])}", unsafe_allow_html=True)
            st.caption(pct(r["expected_90d_pct"]) + " (90d)")
        with c5:
            st.write(r["signal_headline"])
            st.caption(f"Hold-window: {r['hold_window']}")

st.markdown("---")
st.markdown("### Stats summary")
st.caption(
    "Hover over a column header to see what it means. **Ens. Dir. % vs Naive Dir. %** "
    "is the honesty check — if our ensemble isn't beating the dumb 'tomorrow = today' "
    "baseline by a clear margin, the trust grade will be C or worse."
)
st.dataframe(
    df_summary[
        [
            "symbol", "name", "spot_aud", "cagr_pct", "vol_pct", "max_dd_pct",
            "ensemble_directional_pct", "naive_directional_pct",
            "trust_grade", "regime", "signal",
        ]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "symbol": st.column_config.TextColumn("Symbol", help="Ticker. ASX names end in .AX."),
        "name": st.column_config.TextColumn("Name", help="Plain-English company name."),
        "spot_aud": st.column_config.NumberColumn(
            "Spot (A$)",
            help="Most recent closing price, converted to AUD using historical FX for US stocks.",
            format="%.2f",
        ),
        "cagr_pct": st.column_config.NumberColumn(
            "CAGR %",
            help=(
                "Compound Annual Growth Rate over the 20-year history. "
                "The constant yearly return that would have got you from "
                "start to today's price."
            ),
            format="%.1f",
        ),
        "vol_pct": st.column_config.NumberColumn(
            "Vol %",
            help=(
                "Annualised volatility — how much the price wobbles year to "
                "year. Higher = bumpier ride. Determines position-size scaling."
            ),
            format="%.1f",
        ),
        "max_dd_pct": st.column_config.NumberColumn(
            "Max DD %",
            help=(
                "Maximum Drawdown — the worst peak-to-trough fall in the "
                "20-year history. -50% means it once fell by half before "
                "recovering."
            ),
            format="%.1f",
        ),
        "ensemble_directional_pct": st.column_config.NumberColumn(
            "Ens. Dir. %",
            help=(
                "How often the ensemble model (prophet+holt-winters+arima) "
                "called the up/down direction correctly in walk-forward "
                "backtest. Above 55% is meaningful; 50% is a coin flip."
            ),
            format="%.1f",
        ),
        "naive_directional_pct": st.column_config.NumberColumn(
            "Naive Dir. %",
            help=(
                "How often the dumb 'tomorrow = today' baseline got the "
                "direction right. The ensemble must beat this by a clear "
                "margin to earn an A or B trust grade."
            ),
            format="%.1f",
        ),
        "trust_grade": st.column_config.TextColumn(
            "Trust",
            help=(
                "A-F grade based on how reliable our forecasts have been on "
                "this stock historically, net of fees + tax. C or worse = "
                "no GO signal will fire here."
            ),
        ),
        "regime": st.column_config.TextColumn(
            "Regime",
            help=(
                "Current market mood for this stock (bull / bear / sideways) "
                "from a Hidden Markov Model. GO signals are suppressed in bear."
            ),
        ),
        "signal": st.column_config.TextColumn(
            "Signal",
            help="GO / WAIT / AVOID — the action column. Default is WAIT.",
        ),
    },
)

render_disclaimer()
