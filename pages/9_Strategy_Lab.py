"""Strategy Lab - toggle enhancements and see how they change the numbers.

This is the honesty engine for FEATURES, not just stocks. Every "smart"
addition gets tested the same way: pick a stock, backtest with the toggle
OFF, backtest with it ON, look at the lift.

Once you find a combo that consistently helps, click "Apply globally" and
the rest of the app (Dashboard, Forward Outlook, Today's Playbook) starts
using those toggles too.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_pipeline import analyse_one
from core.backtest import backtest_all, trust_grade
from core.data import fetch_history
from core.fx import normalise_to_aud
from core.macro import macro_snapshot
from core.regime import detect_regime
from core.regime_grade import stratified_grade
from core.settings import (
    Enhancements,
    SESSION_KEY,
    all_off,
    all_on,
    from_session as enh_from_session,
    to_session as enh_to_session,
    with_only,
)
from core.tickers import WATCHLIST, by_symbol
from core.volatility import forecast_vol, is_arch_available
from ui_helpers import grade_badge, page_setup, pct, render_disclaimer

page_setup("Strategy Lab")

st.markdown(
    "Each toggle below is an opt-in tweak to the default analysis. Flip them on, "
    "compare backtest metrics ON vs OFF, and only enable globally if the lift is real. "
    "**Default is everything OFF** - that is the v1 baseline you've been using."
)

# ----- Sidebar: current global settings -----
with st.sidebar:
    st.header("Current global toggles")
    current = enh_from_session(st.session_state)
    st.caption(f"Active: `{current.short_label()}`")
    if current.any_active() and st.button("Reset to vanilla"):
        enh_to_session(st.session_state, all_off())
        st.rerun()

# ----- Toggle controls -----
st.markdown("### Enhancements")

c1, c2, c3 = st.columns(3)
with c1:
    use_garch = st.toggle(
        "1. GARCH volatility",
        value=False,
        help=(
            "Forecasts the next 90 days of volatility using GARCH(1,1). "
            "Used for: shrinking position size when GARCH expects a storm, "
            "growing it when GARCH expects calm."
        ),
    )
    if not is_arch_available():
        st.caption(":warning: `arch` package not installed - falls back to rolling stdev.")
with c2:
    use_macro = st.toggle(
        "2. Cross-asset confirmation",
        value=False,
        help=(
            "Checks parent index regime (^GSPC for US, ^AXJO for ASX) and VIX. "
            "When ON: GO signals are downgraded to WAIT if the macro mood is hostile "
            "(bear index OR VIX > 30)."
        ),
    )
with c3:
    use_regime_grade = st.toggle(
        "3. Regime-stratified trust grade",
        value=False,
        help=(
            "Replaces the all-history trust grade with one computed only on past "
            "folds whose start-regime matches today's. Falls back to all-history "
            "if there are < 5 same-regime folds."
        ),
    )

candidate = Enhancements(
    use_garch=use_garch,
    use_macro_confirm=use_macro,
    use_regime_grade=use_regime_grade,
    label="lab-candidate",
)

st.divider()

# ----- Per-stock comparison -----
st.markdown("### Per-stock backtest comparison")

stock_options = [t.symbol for t in WATCHLIST]
default_idx = stock_options.index("MSFT") if "MSFT" in stock_options else 0
symbol = st.selectbox("Stock to test on", stock_options, index=default_idx)
broker = st.session_state.get("broker", "Stake")

if st.button("Run comparison: ON vs OFF", type="primary"):
    t = by_symbol(symbol)
    with st.spinner(f"Backtesting {symbol} with both configurations..."):
        df_native = fetch_history(symbol, years=20, adjusted=True)
        df = normalise_to_aud(df_native, t)

        bt = backtest_all(df, horizon_days=90, market=t.market, broker=broker, max_folds=40)
        rg = detect_regime(df)
        vanilla_grade = trust_grade(bt)

        rows = [{
            "Configuration": "Vanilla (all OFF)",
            "Trust grade": vanilla_grade.grade,
            "Trust score": f"{vanilla_grade.score:.0f}",
            "Directional %": f"{bt['ensemble'].directional_accuracy_pct:.1f}",
            "MAPE %": f"{bt['ensemble'].mape_pct:.2f}",
            "Net AUD %": f"{bt['ensemble'].paper_trade_net_return_pct_aud:+.1f}",
            "Notes": "Baseline - what v1 of TRADEON gave you.",
        }]

        # Regime-stratified grade
        if use_regime_grade:
            srg = stratified_grade(df, bt, rg.label, horizon_days=90)
            rows.append({
                "Configuration": "+ regime-grade",
                "Trust grade": srg.grade.grade,
                "Trust score": f"{srg.grade.score:.0f}",
                "Directional %": f"{srg.per_regime_metrics.get(rg.label, {}).get('directional_pct', 0):.1f}",
                "MAPE %": f"{srg.per_regime_metrics.get(rg.label, {}).get('mape_pct', 0):.2f}",
                "Net AUD %": "(uses vanilla)",
                "Notes": srg.interpretation,
            })

        # GARCH analysis
        if use_garch:
            vol = forecast_vol(df, horizon_days=90)
            rows.append({
                "Configuration": "+ GARCH",
                "Trust grade": "(unchanged)",
                "Trust score": "(unchanged)",
                "Directional %": "(unchanged)",
                "MAPE %": "(unchanged)",
                "Net AUD %": "(unchanged)",
                "Notes": (
                    f"Position size x{1 / vol.vol_ratio:.2f}, CI band x{vol.vol_ratio:.2f}. "
                    f"{vol.interpretation}"
                ),
            })

        # Macro analysis
        if use_macro:
            macro = macro_snapshot(t.market)
            rows.append({
                "Configuration": "+ macro confirm",
                "Trust grade": "(unchanged)",
                "Trust score": "(unchanged)",
                "Directional %": "(unchanged)",
                "MAPE %": "(unchanged)",
                "Net AUD %": "(unchanged)",
                "Notes": (
                    f"Macro mood: **{macro.mood}**. "
                    f"{'Would BLOCK live GO signal.' if macro.mood == 'hostile' else 'Would NOT block live GO signal.'} "
                    f"{macro.interpretation}"
                ),
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.caption(
            "Trust score is the headline number to watch. A lift of >5 points is meaningful, "
            "<5 is noise. GARCH and macro don't change the trust grade directly - they change "
            "what HAPPENS at trade time (sizing, GO/WAIT override)."
        )

st.divider()

# ----- Apply globally -----
st.markdown("### Apply to live signals")
st.caption(
    "Once you've found a combo that helps, click below to make Dashboard, Forward "
    "Outlook and Today's Playbook use those toggles too. Each new combination "
    "triggers a fresh analysis pass on next visit (cached after that)."
)

a1, a2 = st.columns(2)
with a1:
    if st.button(f"Apply '{candidate.short_label()}' globally", type="primary"):
        enh_to_session(st.session_state, candidate)
        st.success(
            f"Active toggles set to `{candidate.short_label()}`. Visit any other page "
            "to see the effect. Note: the watchlist will re-analyse with the new toggles "
            "on first visit (cached after)."
        )
with a2:
    if st.button("Reset all toggles globally"):
        enh_to_session(st.session_state, all_off())
        st.success("All toggles cleared. Vanilla v1 behaviour restored.")

st.divider()

# ----- Guide -----
with st.expander("How to use this lab effectively", expanded=False):
    st.markdown("""
**The honest workflow:**

1. **Pick a stock you care about** (e.g. MSFT or BHP.AX).
2. **Toggle ONE feature ON, run the comparison.** Note the trust score lift.
3. **Try another stock.** Does the same toggle help there too?
4. **Repeat across 3-5 stocks** before concluding. A toggle that helps 4/5 stocks
   is real. A toggle that helps only the one stock you tested is probably noise.
5. **Stack toggles only after each one is individually proven.** If GARCH alone
   gives +3 trust points and macro alone gives +5, both ON should be roughly +6
   to +8. If it's much lower, they're stepping on each other.
6. **Apply globally only when the lift is consistent and meaningful** (>5 trust
   points across most of the watchlist).

**What to watch for:**

- A toggle that *lowers* trust scores - leave it OFF.
- A toggle that helps high-vol stocks but hurts steady ones - apply selectively.
- "(unchanged)" in some columns is normal: GARCH affects sizing, not predictions;
  macro affects the GO/WAIT verdict, not predictions.

**Realistic expectations:**

- A combined lift of +5 to +15 trust points across the watchlist is a *very*
  good result.
- +20 or more is suspicious - check whether you're inadvertently overfitting
  to recent data.
- 0 or negative on most stocks means the toggle just isn't earning its keep
  for this watchlist - that's also useful information.
    """)

with st.expander("What does each toggle actually do under the hood?"):
    st.markdown("""
**1. GARCH volatility (`core/volatility.py`)**
- Fits a GARCH(1,1) model to daily returns.
- Forecasts annualised volatility for the next 90 days.
- Output: a multiplier in [0.5, 1.5] applied to position size, and a multiplier
  in [0.7, 1.5] applied to CI bands.
- When OFF: position sizing uses simple trailing 90-day stdev (current v1 behaviour).
- Cost: tiny (one GARCH fit per ticker, < 1 second).

**2. Cross-asset confirmation (`core/macro.py`)**
- Fetches ^GSPC (US) or ^AXJO (ASX) and runs the same regime detection on it.
- Fetches ^VIX for US fear index.
- Returns mood: favourable / neutral / hostile.
- When ON: a GO signal is downgraded to WAIT when mood = hostile. Never creates
  new GOs - only suppresses bad ones.
- Cost: two extra fetches (cached for 1 hour).

**3. Regime-stratified trust grade (`core/regime_grade.py`)**
- Labels every historical backtest fold by the regime at the fold's START.
- For the trust grade, uses ONLY folds whose start-regime matches today's regime.
- When fewer than 5 same-regime folds exist, falls back to vanilla all-history.
- Cost: zero extra compute - reuses existing backtest output.
    """)

render_disclaimer()
