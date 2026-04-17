"""TRADEON landing page.

Run with: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from core.forecast import PROPHET_AVAILABLE
from core.tickers import WATCHLIST
from ui_helpers import broker_picker, capital_input, page_setup, render_disclaimer

page_setup("TRADEON", icon="")

st.markdown(
    "##### Self-validating stock outlook for an Australian retail trader. "
    "All projections computed locally from raw historical price data."
)

with st.sidebar:
    st.header("Settings")
    broker = broker_picker()
    capital = capital_input()
    st.caption(f"Watchlist: **{len(WATCHLIST)}** stocks")
    st.session_state["broker"] = broker
    st.session_state["capital"] = capital

st.markdown("### Welcome")
st.markdown(
    """
    TRADEON looks at 20 years of raw price history for an Australian-tilted watchlist
    of prominent stocks (ASX large caps + a few US big-tech names) and runs an
    in-house ensemble of forecasting models. Every prediction is graded against what
    really happened - we earn your trust BEFORE issuing any recommendations.

    **Default state for every stock is WAIT.** A green GO signal only appears when
    multiple independent indicators agree. Most days you'll see no green lights -
    that is the system protecting you from low-quality trades.
    """
)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("####  Get started")
    st.markdown(
        "1. Open the **Dashboard** to see today's status across the watchlist.\n"
        "2. Click into a stock on **Deep Dive** to see its 20-year analysis.\n"
        "3. Check **Forward Outlook** for active GO signals."
    )
with col2:
    st.markdown("####  How honest is it?")
    st.markdown(
        "Every metric is reported BOTH on its own AND vs a naive 'tomorrow = today' "
        "baseline. If our ensemble doesn't beat the naive baseline on a stock, the "
        "trust grade drops to D or F and we ignore it."
    )
with col3:
    st.markdown("####  New to investing?")
    st.markdown(
        "Visit the **Learn** page for plain-English explainers on broker accounts, "
        "order types, settlement, AU CGT, dividends, and a glossary of every metric "
        "used in the app."
    )

st.markdown("---")

with st.expander("Engine status"):
    import sys
    st.write(f"**Python:** {sys.version.split()[0]}")
    st.write(f"**Prophet available:** {'Yes' if PROPHET_AVAILABLE else 'No (fallback to Holt-Winters + ARIMA)'}")
    st.write(f"**Watchlist size:** {len(WATCHLIST)} stocks")
    if not PROPHET_AVAILABLE:
        st.caption(
            "Prophet isn't installed in this environment, so the ensemble runs on "
            "Holt-Winters + ARIMA. Forecasts still work; accuracy on big-tech names "
            "is slightly lower than with Prophet enabled. To add Prophet locally, "
            "use Python 3.11/3.12 and run `pip install prophet`. On Streamlit "
            "Community Cloud, Prophet installs automatically (Python 3.11 is pinned "
            "via runtime.txt)."
        )

render_disclaimer()
