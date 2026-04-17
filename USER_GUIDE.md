# TRADEON — User Guide

A plain-English, printable manual. Designed to be read on screen, on your tablet, or printed out and kept beside your laptop.

If something is unclear, every page in the app also has a **Learn** tab and a **Help** tab — same content as this document.

> **Important:** TRADEON gives you statistical decision support based on historical price data. It is NOT financial advice. You alone are responsible for any money you put into the market. Past performance does not guarantee future results.

---

## Contents

1. [What TRADEON does in one paragraph](#1-what-tradeon-does-in-one-paragraph)
1.5. [How it all fits together — the mental model](#15-how-it-all-fits-together)
2. [Your first session — a 15-minute walkthrough](#2-your-first-session)
3. [Reading the Dashboard](#3-reading-the-dashboard)
4. [Reading a Deep Dive](#4-reading-a-deep-dive)
5. [Using the Backtest Lab](#5-using-the-backtest-lab)
6. [Acting on a GO signal](#6-acting-on-a-go-signal)
6.5. [The Strategy Lab — toggling enhancements](#65-the-strategy-lab--toggling-enhancements)
6.6. [Recommended toggle starter packs](#66-recommended-toggle-starter-packs)
6.7. [Reading the diagnostic captions on Forward Outlook](#67-reading-the-diagnostic-captions-on-forward-outlook)
7. [The trust grade in plain English](#7-the-trust-grade-in-plain-english)
8. [Common questions](#8-common-questions)
9. [What to do if something looks broken](#9-what-to-do-if-something-looks-broken)
10. [Glossary](#10-glossary)

---

## 1. What TRADEON does in one paragraph

You give TRADEON a list of stocks you might want to trade (already configured: 15 ASX large caps and 6 US big-tech names). It downloads 20 years of daily prices for each one, runs five different statistical forecasting models, and grades itself on how accurate those models have been at predicting the recent past. Every now and then — usually no more than a few times a quarter — several signals line up at once on a particular stock and TRADEON issues a short-to-medium-term **GO** signal with a suggested entry window, exit date, stop-loss level, and expected after-fee, after-tax AUD return. Most days, on most stocks, TRADEON simply says **WAIT**. That is the correct default behaviour.

You can also turn on up to **five opt-in enhancements** in the Strategy Lab page — they let you stress-test the system, sharpen the forecasts, or add safety filters. They all default to OFF so you always have the v1 baseline to compare against.

---

## 1.5 How it all fits together

If you read nothing else, read this. It's the mental model for what's happening when you open the app.

### The pipeline in one diagram

When you open the Dashboard or Forward Outlook, every stock in your watchlist runs through this pipeline once (then results are cached for an hour):

```text
                        Raw 20 years of OHLCV
                          (yfinance, cached)
                                  │
                                  ▼
                   Convert US prices to AUD using
                       historical AUD/USD
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
        REGIME              FORECAST              EVIDENCE
    bull / bear /      Naive, Seasonal,       Hold-window match
      sideways         Holt-Winters,          Technicals (RSI/MACD)
       (HMM)           ARIMA, Prophet         Earnings windows
                       → ENSEMBLE              Stop-loss level
                                              Position size
                                  │
                                  ▼
                          TRUST GRADE A-F
                  (walk-forward backtest of the
                   ensemble vs naive baseline,
                       net of fees + tax)
                                  │
                                  ▼
              ┌──────── decide() AND-gate ────────┐
              │  Trust ≥ B  AND  regime ≠ bear    │
              │  AND hold-window match            │
              │  AND positive expected return     │
              │  AND a technical confirmation     │
              │  AND no earnings window           │
              └─────────────────┬─────────────────┘
                                ▼
                     GO  /  WAIT  /  AVOID
                                │
              (post-decision safety filters, opt-in)
                                │
            ┌─── MACRO TOGGLE ──┼── BREAKER TOGGLE ───┐
            ▼                   ▼                     ▼
   Parent index in bear?   Down >15% in 30d?
   VIX > 30?                                      → force WAIT
            │                   │
            └─── if any trips: GO → WAIT ─────────────┘
                                │
                                ▼
                     Final signal shown to you
                     (with full trade plan if GO)
```

### The five enhancement toggles, in order of how they affect the pipeline

| # | Toggle | Where it plugs in | What it changes |
|---|--------|-------------------|-----------------|
| 4 | Recency-weighted ensemble | **Forecast step** | Re-weights the 3 sub-models by recent accuracy. Changes the actual forecast number going into the decider. |
| 1 | GARCH volatility | **Position size step** | Doesn't change the GO/WAIT verdict at all. Adjusts how big a position you take *if* GO fires. |
| 3 | Regime-stratified trust grade | **Trust-grade step** | Replaces the all-history grade with one computed only from same-regime quarters. Can promote or demote a stock's grade. |
| 2 | Cross-asset confirmation | **After the decider** (safety filter) | If the parent index is bear OR VIX > 30, force any GO down to WAIT. |
| 5 | Drawdown circuit-breaker | **After the decider** (safety filter) | If the stock is down >15% from its 30-day peak, force any GO down to WAIT. |

### Why five toggles instead of just always-on

Three reasons:

1. **You can SEE the impact.** Without toggles, you'd have to take it on faith that "macro confirmation helps". With the Strategy Lab you flip it on, run a real backtest, and see the trust score actually move.
2. **What helps MSFT may hurt CSL.AX.** A toggle that's perfect for high-volatility US tech can be unnecessary noise on a steady ASX dividend stock. You decide which to keep on.
3. **Each toggle is a different lever.** The recency-weighted toggle actually changes what the model predicts. The drawdown breaker doesn't change the prediction at all — it overrides the verdict. They're different kinds of help, so they're separate switches.

### What "vanilla" means

When all five toggles are OFF, you get the v1 baseline behaviour:
- Equal-weight ensemble of prophet/holt-winters/arima
- Trust grade computed across all historical quarters (any regime)
- Position size scaled by trailing 90-day stdev only
- No macro filter; a single-stock GO can fire even in a bear market
- No drawdown filter; a falling-knife stock can still be issued a GO

That's the conservative-but-naive starting point. The toggles let you trade off "more conservative" vs "more aware" vs "more reactive" without rebuilding anything.

### What stays the same regardless of toggles

- **The trust grade is always honest.** It's always the result of a real walk-forward backtest. Even if you turn on every enhancement, if the model can't beat naive on a stock, that stock stays at C/D/F.
- **The default is always WAIT.** GO requires multiple signals to align. Toggles only ever add filters or refine forecasts — they never lower the bar for what counts as GO.
- **All numbers are still net of fees and AU CGT.** Every backtest, every projection, every position size includes broker fees and tax. The toggles don't change this.
- **Nothing leaves your machine.** Even with toggles on, the only thing entering the system is OHLCV from yfinance. No news scraping, no LLM commentary, no analyst targets.

---

## 2. Your first session

Allow about 15-20 minutes of clock time. Most of it is waiting while the computer thinks.

### Step 1 — open the app

- **Tablet or another device:** open `https://tradeon-7.streamlit.app` (your custom URL).
- **Laptop locally:** open PowerShell, run `streamlit run app.py` in the project folder, click the URL it prints.

### Step 2 — set your defaults in the sidebar

In the left sidebar:

- **Your broker** — pick the one you actually use (CommSec, Stake, Pearler, or SelfWealth). This determines the fees that get baked into every backtest.
- **Capital per trade (AUD)** — the typical AUD amount you'd commit to one position. Default is $1,000. This sizes the example trades and the hypothetical return calculations.

These settings persist across pages while the app stays open.

### Step 3 — open the Dashboard

Click **Dashboard** in the left navigation.

The first time you do this, the system has work to do — it loads 20 years of data for 21 stocks and runs walk-forward backtests on each.

- **On a normal day:** roughly **30-90 seconds**. The price data is bundled into the repo and refreshed every weekday morning by a GitHub Action, so the slow yfinance download step is already done. Streamlit only has to run the math.
- **On a "first deploy ever" day or a day the nightly refresh failed:** **10-25 minutes**, because the bundled cache is missing or stale and Streamlit has to refetch every symbol from yfinance. Make a coffee. This should happen rarely.

Subsequent visits within an hour are instant (results are cached in memory).

While you wait, you can navigate to other pages — they don't share the same long-running calculation.

### Step 4 — read the Dashboard

Once it loads you'll see a table with one row per stock. The columns that matter most:

- **Trust grade** — A through F. How reliable is the model on this stock? A = great, F = useless.
- **Regime** — bull / bear / sideways. What does the recent market behaviour look like for this stock?
- **Signal** — GO / WAIT / AVOID. What is the system telling you to do today?

The vast majority of rows will read **WAIT**. That is normal. See [section 6](#6-acting-on-a-go-signal) for what to do when a GO appears.

### Step 5 — pick one stock and Deep Dive it

Choose a stock you've heard of (Microsoft, BHP, Apple — anything). Click **Deep Dive** in the navigation, select that stock from the dropdown.

Spend five minutes scrolling. You'll see:

- A 20-year price chart with bear-market periods shaded
- Key statistics (CAGR, volatility, max drawdown)
- A heatmap of best historical buy-month/sell-month combinations
- A "$1,000 hypothetical trade" calculator
- The full backtest report behind that stock's trust grade

This is the most informative single page in the app. Use it whenever you want to understand a specific stock.

### Step 6 — visit the Backtest Lab once

Click **Backtest Lab**. Pick MSFT, model = `ensemble`, horizon = 90 days. Hit it.

This shows you the literal "what I would have predicted vs what really happened" chart, repeated across many quarters of the past 20 years. This is the page that builds intuition for how much (or how little) to trust the system. Spend two minutes looking at it.

### Step 7 — check the Forward Outlook

Click **Forward Outlook**. This page only shows stocks where TRADEON is currently issuing a GO signal. Most days it will be empty. **That is correct behaviour, not a bug.**

If there IS a GO signal showing, scroll down to the "How to actually place this trade" expandable section. It will give you broker-specific instructions.

### Step 8 — bookmark / save to home screen

- **iPad / iPhone Safari:** tap the share button → "Add to Home Screen"
- **Android Chrome:** menu → "Add to Home screen"
- **Desktop:** bookmark the URL

You're done with first-time setup.

---

## 2.5 The "Today's Playbook" panel

Once the Dashboard has been run at least once in your current browser session, the landing page automatically shows a **Today's Playbook** panel at the top. It's the fastest way to answer "what should I look at right now?" without scrolling through 21 watchlist rows.

The panel has three parts:

- **Headline banner** (green/grey/red) — the single best GO opportunity right now, OR a friendly "no GO signals, sit tight" with a runner-up to keep an eye on.
- **Watchlist mood** — bull / bear / sideways count across all 21 stocks. If more than half are in bear, it explicitly tells you the market is defensive and GO signals will be sparse.
- **One to watch** — the most promising currently-active seasonal hold-window that hasn't quite triggered a full GO yet. A "watch this in case other conditions line up" pointer.

If you land on the home page before the Dashboard has run in this session, you'll see a "Compute playbook now" button instead — it triggers the same heavy first-load work the Dashboard does.

## 3. Reading the Dashboard

The Dashboard is your daily glance. Every column tells you something specific.

| Column | What it means | When to care |
|--------|---------------|--------------|
| **Symbol** | The ticker (e.g. MSFT, BHP.AX) | Always |
| **Name** | Plain English company name | Always |
| **Last close (AUD)** | Most recent closing price, converted to AUD for US stocks | When sizing a trade |
| **Trust grade** | A-F reliability of the model on this stock | This is the most important column |
| **Regime** | Bull / Bear / Sideways — current market mood | A bear regime means GO signals will be suppressed |
| **Signal** | GO / WAIT / AVOID | This is the action column |
| **Forecast lift** | Predicted AUD % move over next 90 days, after fees + tax | Sense check on the GO signal |
| **Pattern strength** | How seasonal/repeatable this stock's behaviour is | High = the system has more to work with |

Sort the table by **Trust grade** to see your most reliable stocks at the top. Stocks with grade D or F are best ignored — the system has explicitly admitted it doesn't understand them well.

The Dashboard also has a **Refresh** button at the top. Use it sparingly — every refresh re-runs the heavy backtests. Once a day is plenty.

---

## 4. Reading a Deep Dive

A Deep Dive is a full report on one stock. Read it top-to-bottom the first time, but in normal use you'll skim to the section you care about.

### 4.1 Price chart with regime shading

The 20-year price line, with red bands marking historical bear-regime periods. Look for: how many bears has this stock survived? Did it recover quickly?

### 4.2 Key statistics

- **CAGR** — annualised return if you'd just bought and held for 20 years
- **Volatility** — how much the price wobbles year to year (lower = calmer)
- **Max drawdown** — the worst peak-to-trough fall in 20 years
- **Sharpe ratio** — return per unit of risk (higher is better; >1 is good)
- **Pattern strength** — how repeatable the seasonal cycles are

### 4.3 Best historical hold-windows

A table and heatmap showing the most profitable buy-month / sell-month combinations across 20 years. Example output: "BHP bought late October, sold late February — average gain 8.2%, hit rate 73%, 14 of 19 years profitable."

This is the heart of the short-to-medium-term seasonal strategy. If a hold-window has a hit rate above 70% with reasonable average gain, that's a real pattern worth knowing about.

### 4.4 Quarterly + monthly seasonality

Two bar charts showing average return by quarter and by month over 20 years. Look for: months that are consistently green (good buying months) vs consistently red (avoid).

For ASX stocks, watch June especially — it's the EOFY tax-loss selling month. The app explicitly flags this if it's a big effect on the stock you're viewing.

### 4.5 $1000 hypothetical trade calculator

Enter "I bought $1,000 worth on date X, sold on date Y" and see what would have actually happened, after broker fees and AU CGT, in AUD. Use this to sanity-check the upcoming hold-window suggestion: "If I had done this trade in each of the last 5 years, would I have actually made money?"

### 4.6 Backtest summary

The walk-forward backtest table behind that stock's trust grade. Columns:

- **Fold** — which historical period this row was tested on
- **Predicted return** — what the model said
- **Actual return** — what really happened
- **Direction match** — did it call up vs down correctly?

Scroll through this to see if the model's mistakes are biased one way (always too optimistic? always missed crashes?). That bias matters more than the average error.

---

## 5. Using the Backtest Lab

The Backtest Lab is for understanding HOW a model has performed historically, not for issuing live signals.

Workflow:

1. Pick a stock.
2. Pick a model. Start with `ensemble` (the default) — it's the one that powers the live signals. Try `naive` too as a sanity check — naive just predicts "tomorrow = today" with no logic.
3. Pick a horizon (30 to 180 days). For your "buy now, sell in a few months" strategy, 60-90 days is the right range.
4. Pick a **history range**. The default ("All available, up to 60 folds") covers roughly the last 15 years of quarterly forecasts — so you can see what TRADEON would have predicted for early 2025 and check it against what actually happened. The "Last 5 years" option is faster but gives you only the most recent ~20 quarters.
5. Read the metrics:
   - **MAPE** — average percentage error. Below 10% is decent for stocks. Above 25% means the model is essentially guessing.
   - **Directional** — what % of the time the model called the up/down direction correctly. Above 55% is meaningful.
   - **CI coverage** — what % of actuals fell within the model's stated confidence range. Closer to 80% is healthy.
   - **Paper-trade net AUD** — what you would have made/lost trading this every fold, after fees and tax.
6. Look at the chart. Are predictions roughly tracking actuals, or are they all over the place? The "Coverage" caption tells you exactly which date range the chart covers.

**Compare ensemble to naive on the same stock.** If naive's paper-trade return is similar to ensemble's, the model is adding nothing useful for that stock — its trust grade should be C or worse.

> **Did the chart used to stop in 2018?** Yes — the v1 backtest defaulted to keeping only the *oldest* 20 folds. v1.2 changed this to keep the *most recent* 60 folds, so you now see predictions all the way up to the most recent completed quarter. If you only want a quick test, use the "Last 5 years" preset.

---

## 6. Acting on a GO signal

The day will come when you visit the Forward Outlook page and see a GO signal. Here's the disciplined way to act on it.

### Pre-checklist (before placing any trade)

- [ ] **Trust grade is A or B?** If it's only C, treat the signal as suggestive, not actionable.
- [ ] **Regime is bull or sideways?** Never act on a GO signal during a bear regime — the decider shouldn't have issued it, but double-check.
- [ ] **The hold-window's historical hit rate is above 65%?** Found on the Deep Dive page.
- [ ] **No earnings volatility window is active?** Shown on the Forward Outlook plan.
- [ ] **The expected return after fees + tax is materially positive?** A predicted +1.5% net AUD over 90 days is not worth the risk. Aim for +5% net or higher.
- [ ] **You can afford to lose this entire position.** Never trade money you need.
- [ ] **Your total open positions across the watchlist do not exceed your risk tolerance.** TRADEON does not enforce this — that's on you.

### Place the trade

The Forward Outlook page now includes three convenience features in the **"How to actually place this trade"** panel:

- **Clipboard order ticket** — a single line like `LIMIT BUY 12 MSFT @ A$612.50 | stop @ A$580 | target exit 2026-07-15` that you can copy with one click and paste into your broker's order screen or your trade journal.
- **Open [broker]** button — opens your selected broker's site in a new tab. (We don't auto-search the symbol because broker URL formats change without notice; the button takes you to the broker's home page where you search.)
- **View chart on Yahoo Finance** button — a sanity-check tab that reliably opens the symbol's chart, useful for confirming you've got the right ticker and seeing the latest news.

Then in your broker's app:

1. Search for the symbol from the order ticket.
2. Use a **limit order** at the suggested entry price (not a market order).
3. Set the **stop-loss** at the level TRADEON suggests. Most brokers let you attach this to the order, or place a separate conditional sell order immediately after the buy fills.
4. Note the suggested **exit date** in your calendar. Set a reminder.

### Manage the trade

- **Don't watch the price hourly.** Daily check-ins are enough for a 90-day swing trade.
- **If price hits your stop-loss, sell.** No exceptions. The whole point of a stop is that you decided in advance.
- **If price hits the suggested exit date, sell** — even if it's currently down. Holding "until it recovers" is how small losses become big ones.
- **If price hits an unexpected windfall up, consider taking partial profits** — sell half, leave half running with a trailing stop. (TRADEON doesn't compute trailing stops yet — see Improvements doc.)

### After the trade

The **Trade Journal** page (left nav) is the right place to record this. Two flows:

- **When you BUY** — open the Journal, pick "Open new trade (buy)", fill in ticker, buy date, price per share, shares. Optionally record what TRADEON's signal and predicted % move were at the time. Click Add trade.
- **When you SELL** — open the Journal, pick "Close existing trade (sell)", select the open trade, enter sell date and price. The journal computes net AUD after fees and CGT, days held, and (if you recorded TRADEON's prediction) how far off the prediction was.

The summary panel at the top of the Journal shows your **personal hit rate**, your **average days held**, your **TRADEON prediction error**, and most usefully — your **hit rate on trades you took AGAINST a WAIT signal**. That last metric is the truest test of "should I trust my gut over the system?"

**Backup the journal regularly.** On Streamlit Cloud the data file can vanish on a redeploy or after the app sleeps. Use the Download button at the bottom of the Journal page to save a CSV copy to your laptop or tablet, then Upload to restore.

---

## 6.5. The Strategy Lab — toggling enhancements

TRADEON ships with **five** opt-in enhancements that change how signals are computed. They all default to **OFF** so you can compare against the baseline you trust. Each one earns its keep individually before you turn it on.

### How to use the Strategy Lab

1. Open the **Strategy Lab** page.
2. Pick a stock you care about.
3. Flip ONE toggle on, click **"Run comparison: ON vs OFF"**.
4. Read the table — does the trust score lift by more than 5 points? Does the directional accuracy go up?
5. Try the same toggle on a different stock. If it helps 4 out of 5 stocks, it's a real edge. If it helps only the one you tested, it's noise.
6. When you're confident, click **"Apply globally"** — the rest of the app (Dashboard, Forward Outlook, Today's Playbook) will start using those toggles.

You can always click **"Reset to vanilla"** to go back to v1 baseline behaviour.

### What each toggle does

**1. GARCH volatility forecast**
- Forecasts the next 90 days of volatility using the GARCH(1,1) model — the same model professional risk desks use.
- When ON: position sizes shrink when GARCH expects an above-trend storm and grow when it expects calm. CI bands also breathe.
- Best for: spreading risk evenly across volatile and calm stocks.
- Doesn't change the GO/WAIT decision itself — only what *size* you trade at.

**2. Cross-asset confirmation**
- Checks the parent index (S&P 500 for US, ASX 200 for ASX) and VIX (the US "fear index") before acting on a single-stock GO.
- When ON: a GO signal gets downgraded to WAIT if the parent index is in a bear regime OR VIX > 30 ("panic").
- Best for: avoiding the single biggest source of losses for short-term traders — getting steamrolled by a hostile overall market.
- Never creates new GO signals — only suppresses risky ones.

**3. Regime-stratified trust grade**
- The vanilla trust grade averages performance across all historical regimes (bull, bear, sideways).
- When ON: trust grade is computed only on past quarters whose start regime matches today's regime.
- Best for: getting a more relevant honesty test when conditions today don't match the long-run average.
- Falls back to the vanilla all-history grade if there are fewer than 5 same-regime folds available.

**4. Recency-weighted ensemble** *(added v1.3)*
- The vanilla ensemble averages prophet, holt-winters and arima with **equal** 1/3 weight on every prediction.
- When ON: the three sub-models are weighted by their accuracy over the **last 5 quarterly forecasts** instead. The model that's been getting it right lately gets the biggest say in the next forecast; the one that's been wrong fades into the background.
- Best for: stocks where the underlying behaviour has changed in the last 1-2 years (e.g. a steady dividend payer that suddenly started growing fast). Equal weighting under-weights the model that's caught the change.
- Cost: zero extra compute — re-uses backtest data we've already computed.
- Realistic effect: 2-5 percentage points of directional accuracy on stocks where one sub-model genuinely dominates; near-zero effect on stocks where all three sub-models perform similarly.
- A safety cap stops any one sub-model from taking more than 70% of the vote, so this can't degenerate into "always use whichever model got lucky last quarter".

**5. Drawdown circuit-breaker** *(added v1.3)*
- A hard safety rule: if a stock has fallen more than **15% from its peak in the last 30 trading days**, any GO signal is forced down to WAIT regardless of what the forecast says.
- Best for: avoiding "buy the falling knife" disasters. Statistical models systematically under-predict how long a fast-moving correction can keep going (the Microsoft / CSL / Meta drawdowns of early 2026 are textbook examples).
- Like the macro confirmation toggle, it never creates new GO signals — it only suppresses risky ones.
- The breaker resets automatically as soon as the drawdown shallows out below 15%, so it doesn't lock you out of a stock forever.
- Tunable: defaults are 15% / 30 days. Both numbers can be tightened (more conservative) or loosened (more permissive) in `core/circuit_breaker.py`.

### Honest expectations

A combined lift of +5 to +15 trust points across the watchlist is a *very* good result. +20 or more is suspicious — check whether you're inadvertently overfitting to recent data. 0 or negative on most stocks means the toggle just isn't earning its keep — that's also useful information, and it's the system being honest with you.

### How to read the Strategy Lab comparison table

When you click **"Run comparison: ON vs OFF"** the table shows one row per configuration:

| Row | What it tells you |
|-----|-------------------|
| **Vanilla (all OFF)** | The v1 baseline. Treat this as the "score to beat". |
| **+ regime-grade** | Trust grade re-computed using only the same-regime past quarters. Look at whether the Trust Score moved up or down — sometimes a stock looks worse in its current regime than across all history (that's an honest finding). |
| **+ GARCH** | Doesn't change the trust score; the Notes column tells you the position-size and CI multipliers GARCH would apply right now. |
| **+ macro confirm** | Doesn't change the trust score; Notes tells you whether the macro mood would currently BLOCK or NOT block a live GO. |
| **+ recency-weighted** | Re-runs the backtest with the new ensemble weights, so the Trust Score column is meaningful. The Notes column shows you the actual weight each sub-model got (e.g. `prophet=33%, holt_winters=29%, arima=37%`). |
| **+ drawdown breaker** | Doesn't change the trust score; Notes tells you whether the breaker is currently TRIGGERED or idle on this stock. |

**The trust score is the headline number to watch.** A lift of >5 points across multiple stocks = real edge. <5 points or inconsistent across stocks = noise. Negative = leave the toggle off.

---

## 6.6 Recommended toggle starter packs

You don't have to figure out the optimal combo on day one. Here are three sensible starting configurations.

### Starter pack A — "Conservative defender" (recommended for new users)

**Toggles ON:** macro confirm, drawdown breaker

**Why:** these are the two safety filters. They never create new GO signals — they only suppress GOs that look risky in context. You keep the v1 forecasting behaviour you already trust, but get two extra layers of "should I really be buying this right now?" protection.

**Best for:** anyone who's already comfortable with the v1 baseline and just wants to avoid the obvious traps (buying into a falling knife or against a bearish overall market).

**What to expect:** slightly fewer GO signals overall. Each GO that does fire has cleared an extra two checks.

### Starter pack B — "Sharper forecasts" (if you want better predictions)

**Toggles ON:** recency-weighted, GARCH

**Why:** these two improve the *quality* of the forecast and the *quality* of the position sizing without adding any safety filters. Recency-weighting lets the best-performing sub-model dominate; GARCH right-sizes positions for the actual volatility regime.

**Best for:** users who want their existing GO signals to be more accurate and right-sized, without changing how often they fire.

**What to expect:** GO signals fire at the same rate as vanilla. Each one has a forecast that better reflects which sub-model is currently in form, and a position size that breathes with volatility.

### Starter pack C — "Defender + sharpener" (the most you'd realistically run)

**Toggles ON:** macro confirm, drawdown breaker, recency-weighted, GARCH

**Why:** combines packs A and B. You get sharper forecasts, smarter sizing, and both safety filters. Skip regime-stratified grade unless your watchlist has at least 5 same-regime folds for most stocks (it falls back to vanilla anyway when the data is thin).

**Best for:** users who've already spent some time in the Strategy Lab and confirmed that each of these toggles helps individually on most of the watchlist.

**What to expect:** noticeably fewer GO signals than vanilla (because of the two safety filters). The ones that do fire are doubly-vetted and right-sized.

### When to turn on regime-stratified trust grade

Toggle 3 is the most situational. Turn it ON if:

- The current regime is **bear** or **sideways** AND your trust grades from the vanilla setting feel implausibly high (because the all-history grade was buoyed by years of bull-market accuracy).
- You're noticing the model predicting strong upside on a stock during a clearly weak macro period — regime-stratifying often deflates that.

Leave it OFF if:

- The current regime is **bull** AND your watchlist has reasonable history. The all-history grade and the bull-only grade will be very similar.
- A stock has fewer than 5 same-regime folds — the toggle silently falls back to vanilla anyway, so it's a no-op there.

---

## 6.7 Reading the diagnostic captions on Forward Outlook

When you have any of the new toggles ON, the **Forward Outlook** page adds small caption lines under each GO card that tell you exactly how the toggles influenced the verdict. Here's how to read them.

### Caption: "Volatility forecast (garch(1,1)): expected vol 28.4% vs trailing 24.1% — slightly elevated"

**Toggle:** GARCH

- **garch(1,1)** = the model successfully fit. If it says **rolling-stdev-fallback**, GARCH didn't converge and the system fell back to a simpler trailing-vol estimate (still useful, but less responsive to clustering).
- **Expected vol** = annualised volatility GARCH forecasts for the next 90 days.
- **Trailing vol** = annualised volatility over the trailing 90 days for comparison.
- **"Slightly elevated"** / **"Elevated"** / **"Calm"** = plain-English summary.
- **What it changed:** the position-size metric on the GO card was multiplied by `1/vol_ratio`, so a high-vol forecast shrinks the suggested AUD amount.

### Caption: "Macro: parent ^GSPC neutral; VIX 18.2 (calm). Mood: favourable."

**Toggle:** Cross-asset confirmation

- **Parent index** = ^GSPC for US stocks, ^AXJO for ASX stocks. Its current regime is shown.
- **VIX** = the US fear index. Below 20 = calm, 20-30 = elevated, above 30 = panic.
- **Mood** = `favourable` / `neutral` / `hostile`. Only `hostile` blocks a GO.
- **What it changed:** if mood was `hostile`, this card wouldn't be on this page — its GO would have been forced to WAIT.

### Caption: "Forecast weighting: Last 5 folds: arima has been most accurate (weight 37%); holt_winters least accurate (weight 29%). Vanilla equal-weight would give each 33%."

**Toggle:** Recency-weighted ensemble

- Tells you which sub-model the recency weighting is currently favouring and by how much.
- Sometimes you'll see **"Last 5 folds: all sub-models within ~15% of each other"** — that means the weighting is barely different from vanilla 33% / 33% / 33%, and the forecast is essentially the same as vanilla.
- **What it changed:** the forecast number on this card was computed using these weights instead of 1/3 each.

### Caption: "Circuit-breaker: Recent drawdown -8.2% from peak 612.50 on 2026-04-02. Below the 15% breaker threshold — GO signals not blocked."

**Toggle:** Drawdown circuit-breaker

- Tells you the current drawdown vs the 30-day peak, with the date.
- If you see **"TRIGGERED"** instead of "Below the 15% threshold", this card wouldn't be on this page — its GO would have been forced to WAIT, and the headline of the WAIT card would explain the breaker fired.
- **What it changed:** nothing visible if idle. If triggered, it's the reason a stock that the forecast otherwise liked is sitting in WAIT.

### A worked example

Say you turn on `recency + GARCH + macro + breaker` and visit Forward Outlook. You see one GO card for MSFT with these captions:

```text
Volatility forecast (garch(1,1)): expected vol 24% vs trailing 21% — modestly elevated
Macro: parent ^GSPC bull; VIX 16.4 (calm). Mood: favourable.
Forecast weighting: Last 5 folds: arima has been most accurate (weight 41%)
Circuit-breaker: Recent drawdown -2.1% from peak — GO signals not blocked.
```

Translation: "All four safety/sharpness filters say green. The macro is supportive, the stock isn't falling, ARIMA has been our most accurate forecaster lately, and we'll trim position size slightly because GARCH expects a modest vol uptick." That's a higher-confidence GO than the same card under vanilla settings would have been.

---

## 7. The trust grade in plain English

Forget the formula. Here's the gut-check version.

> "If I had been using TRADEON's predictions for this stock for the last 10 years, would I have made or lost money — net of fees and tax — compared to just doing nothing?"

| Grade | Translation |
|-------|-------------|
| **A** | "I would have made meaningful money. Trust me on this stock." |
| **B** | "I would have made some money. I'm useful here." |
| **C** | "I would have roughly broken even. I don't really understand this stock — neither do I, neither do you." |
| **D** | "I would have lost a bit. Don't act on my signals here." |
| **F** | "I would have lost notable money. Worse than doing nothing. Ignore me on this stock." |

A grade is per-stock. The same model can be A on Microsoft and D on Telstra — that's fine, that's the system being honest.

---

## 8. Common questions

**Q: The Dashboard shows nothing but WAIT. Is it broken?**
A: No. WAIT is the default. It's normal to see no GO signals for days or weeks. The system is being deliberately conservative.

**Q: What if I disagree with TRADEON and want to trade something it says WAIT on?**
A: That's your call. TRADEON is decision support, not a gatekeeper. Go to Backtest Lab first to understand what the system has seen historically. If you still want to trade, you can — but you've removed TRADEON's quality check.

**Q: How often should I check the app?**
A: Once a day is plenty. Once a week is fine. The signals are designed for 30-90 day swings, not day trading. Checking hourly is counterproductive.

**Q: Why is my US stock's price different in TRADEON vs Yahoo Finance?**
A: TRADEON converts US-listed prices to AUD using the historical exchange rate. Yahoo shows prices in USD. The dollar amounts will look different — the % changes will not.

**Q: Can I add a stock that's not in the watchlist?**
A: Yes — edit `core/tickers.py` and add a new entry. Then commit and push (the cloud app will redeploy automatically). Note that small/illiquid stocks may not have enough history for a reliable trust grade.

**Q: What if I lose money on a TRADEON-suggested trade?**
A: Statistically inevitable. Even an A-grade model is wrong sometimes. The grade is about being right MORE often than wrong, net of fees, over many trades. One losing trade doesn't invalidate the system. A run of 5+ consecutive losing trades is when you should pause and look at whether the trust grade has dropped.

**Q: Can TRADEON tell me when to sell something I already own?**
A: Not directly — it's built around fresh entries. As a workaround, look at the stock's Deep Dive: if the regime has flipped to bear or the trust grade has dropped to D/F, that's an honest signal to consider exiting.

**Q: Does TRADEON pay attention to news, earnings reports, or analyst ratings?**
A: Deliberately not. The whole point is that everything is computed from raw prices alone. The user-facing app shows you the computed signals; you're free to overlay your own news judgement on top.

**Q: Is my data private on Streamlit Cloud?**
A: TRADEON doesn't store any personal data. The only thing that travels is OHLCV from yfinance. If you set the app to "Only specific people can view" with Google login, only you see the URL contents.

---

## 9. What to do if something looks broken

| Symptom | Fix |
|---------|-----|
| "Oh no" generic error page | Check the build logs in Streamlit Cloud → "Manage app" |
| Dashboard hangs >30 minutes on first load | Cancel and reload; Streamlit Cloud may have throttled. Try off-peak hours. |
| A specific stock shows no data | Yahoo may have changed its symbol. Edit `core/tickers.py` to remove or update it. |
| Trust grade dropped sharply | Recent market shock — this is the system reacting honestly. Wait a few weeks for it to stabilise. |
| Cloud app is slow to wake | Free tier sleeps after 7 days idle. First visit takes ~30 sec to wake. |
| Local app won't start | Activate the venv (`.\.venv\Scripts\Activate.ps1`) then `streamlit run app.py` |

If you want me (the assistant) to debug, copy the last 30-50 lines of the build/runtime log from "Manage app" and paste them in chat.

---

## 10. Glossary

This is a quick reference. The Learn page in the app has a fuller version with examples.

- **CAGR** — Compound Annual Growth Rate. The constant yearly return that would have got you from start to end.
- **Volatility** — Standard deviation of daily returns, annualised. How wildly a stock swings.
- **Max drawdown** — Biggest peak-to-trough fall in the data window.
- **Sharpe ratio** — Excess return divided by volatility. Higher = better risk-adjusted.
- **MAPE** — Mean Absolute Percentage Error. Average size of the model's mistakes.
- **Directional accuracy** — Fraction of predictions where up vs down was called correctly.
- **CI coverage** — Fraction of actuals that fell inside the model's stated confidence range.
- **Trust grade** — A-F summary of how reliable the model has been on this specific stock historically, net of fees + tax.
- **Naive baseline** — The simplest possible "model": tomorrow's price = today's price. Anything more sophisticated must beat this.
- **Regime** — Current market mood (bull / bear / sideways) as detected from recent return distributions.
- **Hold window** — A historically profitable buy-month / sell-month pair, with a hit rate.
- **Hit rate** — Out of N similar past trades, what fraction were profitable.
- **Stop-loss** — Pre-decided price at which you sell to cap your loss.
- **Position size** — How many AUD to commit to one trade so that all your trades carry similar risk.
- **RSI** — Relative Strength Index, 0-100. Above 70 = overbought, below 30 = oversold.
- **MACD** — Moving Average Convergence Divergence. Trend-following momentum indicator.
- **Bollinger Bands** — Price envelope based on volatility. Touching the upper band = stretched.
- **Market order** — Buy/sell immediately at whatever price is available right now.
- **Limit order** — Buy/sell only if the price reaches your specified level. Always preferred for swing trades.
- **T+2 settlement** — Cash from a sale becomes withdrawable 2 trading days after the trade.
- **CGT discount** — In Australia, holdings of 12+ months have their taxable gain halved.
- **Brokerage fee** — Flat or percentage fee charged by your broker per trade.
- **Franking credits** — Australian tax credit attached to dividends already taxed at the company level.
- **Walk-forward backtest** — Train on history up to date X, predict forward, then check against what actually happened. Repeated across many X's.
- **Ensemble** — Combination of multiple models, each weighted by its recent accuracy.

---

*End of user guide. To print this from the in-app Help page: open the app, go to Help, press Ctrl+P (Windows) or Cmd+P (Mac), choose "Save as PDF" or print directly.*
