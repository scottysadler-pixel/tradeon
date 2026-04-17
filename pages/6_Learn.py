"""Learn - beginner education centre.

Plain-English explainers for someone new to share trading. Plus a full
glossary that doubles as the source of every tooltip in the app.
"""

from __future__ import annotations

import streamlit as st

from core.costs import BROKERS
from core.glossary import GLOSSARY
from core.trade_walkthrough import static_template_help
from ui_helpers import page_setup, render_disclaimer

page_setup("Learn")

st.markdown(
    "Plain-English guides for getting started with share trading in Australia. "
    "Nothing here is financial advice - it's the practical mechanics."
)

with st.expander("**What is a share?**", expanded=False):
    st.markdown(
        """
        A share is a tiny piece of ownership in a company. If Microsoft has issued
        1 billion shares and you own 10, you own 1/100,000,000th of Microsoft.

        **Why does the price move?** Two reasons:
        1. **What the company is worth** changes - new products, profits, scandals.
        2. **What people are willing to pay** changes - mood, news, big investors
            buying or selling.

        Long term, prices follow the company's value. Short term, they follow
        emotion. TRADEON looks for short-term patterns that have repeated reliably
        in the past.
        """
    )

with st.expander("**Opening a broker account in Australia**"):
    st.markdown("To buy shares you need a broker. Common Australian options:")
    for name, bp in BROKERS.items():
        st.markdown(f"- **{name}**: {bp.description}  \n  ASX fee A${bp.asx_fee:.2f}, US fee ~A${bp.us_fee_aud:.2f}")
    st.markdown(
        """
        **CHESS-sponsored vs custodian.**
        - **CHESS-sponsored** (CommSec, Pearler, SelfWealth, Stake-AU): you legally
          own the shares directly via Australia's CHESS register. Safer if the
          broker goes bust.
        - **Custodian** (Stake-US, eToro): the broker holds the shares for you.
          Cheaper fees but the broker is between you and the shares.

        For TRADEON's typical short-hold strategy, fees matter a lot. Stake and
        Pearler are good low-fee starting points.
        """
    )

with st.expander("**Placing a trade - market vs limit orders**"):
    st.markdown(
        """
        - **Market order**: 'Buy now at whatever the price is.' Fast, but in fast
          markets you might pay 1-2% more than the last shown price.
        - **Limit order**: 'Buy ONLY if the price drops to A$X.' You control the
          price but the trade may never happen if the market doesn't reach your
          level.

        TRADEON's trade walkthroughs always recommend **limit orders** with a
        small buffer (typically +0.5%). Safer for beginners and avoids being
        front-run by HFT bots in the opening minutes.
        """
    )

with st.expander("**Trading hours & T+2 settlement**"):
    st.markdown(
        """
        - **ASX**: 10:00 - 16:00 Sydney time (AEST/AEDT). Outside these hours,
          orders queue for the next session.
        - **US (NYSE/NASDAQ)**: 09:30 - 16:00 New York time, which is roughly
          midnight to 07:00 AEST (varies with daylight saving).
        - **T+2 settlement**: when you sell, the cash isn't actually in your
          account for 2 business days. Plan for this if you need the money fast.
        """
    )

with st.expander("**Australian Capital Gains Tax (CGT)**"):
    st.markdown(
        """
        When you sell shares for more than you paid, you owe tax on the **capital
        gain**.

        - Hold for **at least 12 months** before selling and you get the **50%
          CGT discount** - you only pay tax on HALF the gain.
        - Sell **before 12 months** and you pay tax on the **full gain at your
          marginal income tax rate**.

        Example: A$1000 gain on a stock you held for 11 months at a 32.5%
        marginal rate = A$325 tax. Wait one more month = A$162.50 tax. That's
        50% more profit just for waiting.

        TRADEON's net-AUD return numbers always show you both pre-tax and
        post-tax outcomes so you can decide whether a short hold still beats
        waiting for the discount.
        """
    )

with st.expander("**Dividends and franking credits**"):
    st.markdown(
        """
        Many ASX companies pay a **dividend** - a slice of profit, usually paid
        twice a year. Big banks (CBA, NAB, WBC, ANZ) and miners (BHP, RIO) are
        well known for dividends.

        **Franking credits** are an Australian quirk - if a company has already
        paid corporate tax on its profits, it passes you a credit you can use
        against your own income tax. Effectively you get the dividend tax-free
        (or close to it) at most income brackets.

        Note: TRADEON's price charts use **adjusted** prices (back-adjusted for
        dividends and splits) for math, and **unadjusted** prices for chart
        display - matching what you see on Yahoo Finance.
        """
    )

with st.expander("**Common beginner mistakes**"):
    st.markdown(
        """
        1. **Chasing a tip** - by the time you hear it, the move has happened.
        2. **Panic-selling** at the bottom - the worst move at the worst time.
        3. **Ignoring fees on small trades** - a A$10 fee on a A$200 trade is 5%
           you have to make back before you break even.
        4. **Not setting a stop-loss** - hoping a falling stock 'comes back' is
           how big losses happen.
        5. **Trading too often** - more trades = more fees + more chances to be
           wrong.
        6. **Not waiting for the CGT discount** when the gain is large.
        """
    )

with st.expander("**Quick primer (your broker)**"):
    broker = st.session_state.get("broker", "Stake")
    for line in static_template_help(broker):
        st.markdown(f"- {line}")

st.markdown("---")
st.markdown("### Glossary")
st.caption("Every metric used in TRADEON, defined in plain English.")
for term in sorted(GLOSSARY.keys()):
    with st.expander(term):
        st.write(GLOSSARY[term])

render_disclaimer()
