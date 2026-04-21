"""Learn - beginner education centre.

Plain-English explainers for someone new to share trading. Plus a full
glossary that doubles as the source of every tooltip in the app.
"""

from __future__ import annotations

from pathlib import Path
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

# Quick links to downloadable guides
PROJECT_ROOT = Path(__file__).resolve().parent.parent
with st.expander("📚 **Download topic-specific guides**", expanded=False):
    st.markdown("Quick reference guides you can save and read offline:")
    
    guide_cols = st.columns(3)
    
    with guide_cols[0]:
        quick_start = PROJECT_ROOT / "QUICK_START.md"
        if quick_start.exists():
            st.download_button(
                "🚀 Quick Start Guide",
                data=quick_start.read_text(encoding="utf-8"),
                file_name="QUICK_START.md",
                mime="text/markdown",
                help="One-page: what each page does + daily workflow",
                use_container_width=True,
            )
    
    with guide_cols[1]:
        backtest_guide = PROJECT_ROOT / "BACKTEST_LAB_WALKTHROUGH.md"
        if backtest_guide.exists():
            st.download_button(
                "🧪 Backtest Lab Guide",
                data=backtest_guide.read_text(encoding="utf-8"),
                file_name="BACKTEST_LAB_WALKTHROUGH.md",
                mime="text/markdown",
                help="Practice testing without risk - 5 worked examples",
                use_container_width=True,
            )
    
    with guide_cols[2]:
        calendar_guide = PROJECT_ROOT / "CALENDAR_FEATURE_GUIDE.md"
        if calendar_guide.exists():
            st.download_button(
                "📅 Calendar Guide",
                data=calendar_guide.read_text(encoding="utf-8"),
                file_name="CALENDAR_FEATURE_GUIDE.md",
                mime="text/markdown",
                help="Trade exit reminders + upcoming exits panel",
                use_container_width=True,
            )
    
    st.caption("💡 These guides are also in the Help page at the top, and in your project repo.")

st.divider()

with st.expander("**How TRADEON works in 60 seconds (start here)**", expanded=False):
    st.markdown(
        """
        TRADEON does **four** things in order, every time you open the Dashboard:

        1. **Load data** — 20 years of daily prices for each watchlist stock.
           US stocks are converted to AUD using the historical exchange rate.
        2. **Forecast** — five different statistical models (naive, seasonal,
           Holt-Winters, ARIMA, Prophet) each predict the next 90 days. They're
           combined into an **ensemble** prediction that usually beats any
           single model.
        3. **Grade itself** — a **walk-forward backtest** asks "if I'd been
           using this model for the last 10 years on this stock, would I have
           actually made money, after broker fees and AU CGT?" The result is
           the A-F **trust grade**.
        4. **Decide** — only when ALL of the following are true does a stock
           get a GO signal: trust grade A or B, regime bull/sideways, an
           active hold-window matches, forecast lift is materially positive,
           a technical confirms, and no earnings window is active. Otherwise
           you see WAIT (the default) or AVOID.

        That's it. **Most days, most stocks show WAIT.** That is the system
        being conservative on purpose, not failing.

        For the full picture (with diagrams), open the **Help** page.
        """
    )

with st.expander("**The five Strategy Lab toggles in one minute**", expanded=False):
    st.markdown(
        """
        TRADEON ships with five **opt-in** enhancements you can flip on the
        **Strategy Lab** page. They all default OFF so you always have the
        v1 baseline to compare against. Each one earns its keep individually
        before you turn it on globally.

        | # | Toggle | What it actually does | Best for |
        |---|--------|----------------------|----------|
        | 1 | **GARCH volatility** | Forecasts how much the next 90 days will SWING (not where they'll go) and resizes positions accordingly. Doesn't change GO/WAIT — only how big a trade is. | Spreading risk evenly across calm and jumpy stocks. |
        | 2 | **Cross-asset confirm** | Before letting any GO fire, checks the parent index (S&P 500 / ASX 200) and the VIX fear index. If either looks hostile, downgrades GO → WAIT. | Avoiding getting steamrolled by a bad overall market. |
        | 3 | **Regime-stratified grade** | Computes the trust grade only on past quarters that match TODAY's regime, instead of all history. | When today's market doesn't look like the long-run average. |
        | 4 | **Recency-weighted ensemble** | Re-weights the 3 forecast sub-models by recent accuracy instead of equal 33%/33%/33%. | Stocks where one sub-model has clearly been winning lately. |
        | 5 | **Drawdown circuit-breaker** | If a stock has fallen >15% from its peak in 30 days, force any GO → WAIT. | Avoiding "buy the falling knife" disasters. |

        **Recommended starter pack:** turn on toggles **2 + 5** (the two
        safety filters). They never create new GO signals — they only
        suppress risky ones. You keep the v1 forecasting you already trust,
        plus two extra "should I really buy this right now?" checks.

        Full details, tuning guide, and how to read the on-card diagnostics
        live in the **Help** page (sections 6.5-6.7).
        """
    )

with st.expander("**What to do when you see your first GO signal**", expanded=False):
    st.markdown(
        """
        It will happen rarely. When it does, **don't panic-buy**. Work
        through this checklist first.

        **Before placing the trade:**

        - [ ] **Trust grade is A or B?** If only C, treat as suggestive, not actionable.
        - [ ] **Regime is bull or sideways?** Never act on a GO during a bear regime.
        - [ ] **The hold-window's historical hit rate is above 65%?** Found on the Deep Dive page.
        - [ ] **Expected return after fees + tax is materially positive?** A predicted +1.5% net AUD over 90 days isn't worth the risk; aim for +5% net or more.
        - [ ] **You can afford to lose this entire position.** Never trade money you need.
        - [ ] **No earnings volatility window is active?** Shown on the Forward Outlook plan.

        **Place the trade:**

        - Open the **Forward Outlook** page → expand "How to actually place this trade".
        - Click **Copy** on the order ticket — paste into your broker's order screen.
        - **Always use a LIMIT order**, never a market order. Set the limit price as suggested.
        - Set the **stop-loss** at the suggested level. Most brokers let you attach this to the order.
        - Add the suggested **exit date** to your calendar with a reminder.

        **Manage the trade:**

        - Daily check-ins are enough. Stop watching it hourly.
        - **If the price hits your stop-loss, sell. No exceptions.** That's why you set it in advance.
        - **If the exit date arrives, sell** — even if currently down. "Just one more month" is how small losses become big ones.

        **After the trade:** record it in the **Trade Journal** page. The
        journal computes your personal hit rate, your average days held, and
        — most usefully — your hit rate on trades you took AGAINST a WAIT
        signal. That last metric is the truest test of "should I trust my
        gut over the system?"
        """
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
