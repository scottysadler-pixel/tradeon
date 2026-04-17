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
m1.metric("GO signals", int(go_n))
m2.metric("WAIT", int(wait_n))
m3.metric("AVOID", int(avoid_n))
m4.metric("Stocks analysed", len(df_summary))

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
st.dataframe(
    df_summary[
        [
            "symbol", "name", "spot_aud", "cagr_pct", "vol_pct", "max_dd_pct",
            "ensemble_directional_pct", "naive_directional_pct",
            "trust_grade", "regime", "signal",
        ]
    ].rename(columns={
        "spot_aud": "spot (A$)",
        "cagr_pct": "CAGR %",
        "vol_pct": "Vol %",
        "max_dd_pct": "Max DD %",
        "ensemble_directional_pct": "Ens. Dir. %",
        "naive_directional_pct": "Naive Dir. %",
    }),
    use_container_width=True,
    hide_index=True,
)

render_disclaimer()
