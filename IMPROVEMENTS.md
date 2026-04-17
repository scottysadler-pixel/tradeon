# TRADEON — Improvement Ideas (curated, not exhaustive)

Restraint is a feature. The current app does one thing well: it tells you when, on which stocks, the patterns line up — and stays quiet otherwise. Most "improvements" make apps worse by adding noise. The list below is filtered for ideas that **simplify, deepen, or open practical opportunities** without dragging the app toward feature bloat.

Each item has:
- **Tier** — `1` is highest impact and easiest, `3` is "only if you really want it"
- **Effort** — rough build time
- **Risk** — what could go wrong
- **Honest take** — whether I'd actually do it
- **Status** — `BUILT` if shipped, otherwise unmarked

---

## What's already shipped

| Version | Items |
|---------|-------|
| **v1.1** | #1.1 Today's Playbook, #1.2 Trade Journal with self-grading, #1.3 broker deep-link, #1.4 clipboard order ticket, #1.5 "Why this signal?" explainer (in the Forward Outlook reasons expander), #2.4 FX vs stock attribution |
| **v1.2** | Three Tier-2 enhancements as toggleable Strategy Lab features: GARCH(1,1) volatility forecast, cross-asset/macro confirmation, regime-stratified trust grade. Backtest fold-coverage fix (max_folds 60, prefer_recent). |
| **v1.3** | Two Tier-3 enhancements: recency-weighted ensemble (`use_recency_weighted`), drawdown circuit-breaker (`use_drawdown_breaker`). Bundled price cache + nightly GitHub Action refresh (cold-start time 30-90s instead of 10-25min). USER_GUIDE rewritten with mental-model section + toggle starter packs + diagnostic-caption reading guide. |

The items below are all `BUILT` per the table above. They're kept here as the original specs / reasoning, in case you ever want to revisit how something was scoped.

---

## TIER 1 — Highest impact, low cost, fits the existing philosophy

### 1.1 — "Today's Playbook" single-screen view (SIMPLIFIES) — **BUILT (v1.1)**

Add a new top-of-app panel showing exactly three things:

1. The single best GO opportunity right now (or "no good trades right now" if none)
2. Your watchlist's overall mood: how many bull vs bear vs sideways regimes
3. The one thing to watch this week (e.g. "BHP enters its historical seasonal window in 12 days")

Why: collapses everything down to the question you actually came to answer. Reduces decision fatigue.

- **Effort:** 1-2 hours
- **Risk:** Almost none — it's a re-skin of existing data
- **Honest take:** Strongly recommend. This is what daily users actually want.

### 1.2 — Personal trade journal with self-grading (DEEPENS) — **BUILT (v1.1)**

A new page where you log trades you actually placed (manually — no broker integration needed). For each entry: ticker, buy date, buy price, sell date, sell price, AUD invested. The app then:

- Shows your real net AUD return after fees + tax
- Compares it to what TRADEON predicted at the time of entry
- Tracks your personal hit rate vs TRADEON's predicted hit rate
- Flags trades you took against TRADEON's WAIT signal so you can see how often "my gut" beat or lost to "the system"

Stored in a single CSV in `data_cache/journal.csv` (or in Streamlit Cloud's session storage as a fallback).

Why: the trust grade currently grades the model. This grades YOU. Over time you learn whether your interventions help or hurt.

- **Effort:** 3-4 hours
- **Risk:** None — it's purely additive
- **Honest take:** Strongly recommend. This is the single feature most likely to make you a better trader.

### 1.3 — Deep-link to broker's symbol page (OPPORTUNITY — addresses your broker question) — **BUILT (v1.1)**

When a GO signal appears, add a button that opens the broker's web app directly on the right symbol's order ticket. Not the same as automatic ordering — you still review and submit yourself. But it removes 4-5 clicks of friction.

What's possible per broker:

| Broker | Deep link possible? | What it would do |
|--------|---------------------|------------------|
| **Stake (US + ASX)** | Yes — symbol search URL works | Opens Stake on the right ticker; you tap "Buy" and enter quantity |
| **CommSec** | Partial — login redirect, then symbol URL | Lands on the trading screen for that symbol after login |
| **Pearler** | Yes — search URL | Opens Pearler search filtered to the symbol |
| **SelfWealth** | Partial | Lands on the watchlist; you click in |

Why: the gap between "TRADEON says BUY MSFT" and "your finger taps the Buy button" should be as small as possible while still keeping you in control.

- **Effort:** 1-2 hours (just URL templates per broker)
- **Risk:** Broker URL formats can change without notice. Build it as a "best effort" link with a fallback to the broker's homepage.
- **Honest take:** Recommend. Free win.

### 1.4 — Clipboard-copy order ticket (OPPORTUNITY) — **BUILT (v1.1)**

Alongside the deep link, a "Copy order details" button that puts a single line on your clipboard:

```text
LIMIT BUY 12 MSFT @ A$612.50, stop @ A$580, target exit 2026-07-15
```

You then paste this into your broker's order ticket fields (or a notes app, or a spreadsheet). It eliminates transcription errors and gives you a paper trail.

- **Effort:** 30 minutes
- **Risk:** None
- **Honest take:** Recommend. Tiny effort, removes a real source of mistakes.

### 1.5 — "Why this signal?" explainer modal (DEEPENS) — **BUILT (v1.1, lives in the per-card "Why this signal fired (reasons)" expander on Forward Outlook)**

For every GO signal, a button that pops a step-by-step audit:

> "GO signal because:
> ✓ Trust grade A (model has been right 64% of the time on this stock historically)
> ✓ Bull regime (current behaviour matches profitable past periods)
> ✓ Hold-window match: stock has gained avg 7.2% in this calendar window across 19 of 20 past years
> ✓ Forecast lift +6.1% net AUD over 90 days
> ✓ RSI at 52 (not overbought)
> ✓ No earnings volatility window for next 30 days
> ✓ No correlation divergence vs sector peers"

Why: builds trust by making the black box transparent. Also catches your eye if one of the conditions is barely met (e.g. trust grade B-minus, forecast lift only +3%) — useful for borderline calls.

- **Effort:** 1 hour
- **Risk:** None
- **Honest take:** Recommend. Makes the system explainable, not just usable.

---

## TIER 2 — Real value, slightly more thought required

### 2.1 — Signal-change email/push notifications (OPPORTUNITY)

Instead of you remembering to check the app, have it tell you when a stock flips from WAIT to GO.

Options ranked by simplicity:

- **ntfy.sh** (free, open) — the app POSTs to a topic URL when a new GO appears; you subscribe to the topic on your phone via the ntfy app. No accounts, no API keys.
- **Email via SMTP** — requires storing your email password as a Streamlit secret. Works but slightly fiddly.
- **Telegram bot** — requires creating a Telegram bot and storing the token.

But there's a catch: Streamlit Cloud doesn't run scheduled jobs on the free tier. The notification logic only fires when the app is actively loaded. Workarounds:

- **Cheap:** GitHub Actions cron (free, runs every hour) that hits the app's URL or runs the signal calculation directly using the `core/` module. Sends notification if a GO appears.
- **Cheaper:** A laptop scheduled task that does the same thing (only works when laptop is on).

Why: the whole point of swing trading is "buy now, check back in a few months." You shouldn't have to babysit the app.

- **Effort:** 4-6 hours
- **Risk:** Notification spam if the signal logic flickers — needs hysteresis (require 2 consecutive runs before alerting).
- **Honest take:** Recommend if you want to be hands-off. The GitHub Actions + ntfy combo is the cleanest path.

### 2.2 — Drawdown / regime shift alert (DEEPENS)

If the overall watchlist regime tilts strongly to bear, the app shows a top banner: **"Defensive mode: 14 of 21 stocks in bear regime. New GO signals temporarily suppressed."**

Same for individual stocks: if a stock you flagged as "watching" flips from bull to bear, alert you.

Why: protects you from acting on stale GOs in deteriorating markets.

- **Effort:** 1-2 hours
- **Risk:** None
- **Honest take:** Recommend. Pairs naturally with #2.1.

### 2.3 — Multi-quarter forecast view (LOOKS FURTHER)

A page showing each watchlist stock's forecast for **next 4 quarters** as four small line charts in a grid. Lets you see seasonal cycles laid out: "BHP looks weak in Q3 but strong in Q4 — wait for the dip."

Why: matches your stated mental model of "buy this quarter, sell next quarter." Currently the app gives you 90-day point forecasts; this shows the rhythm.

- **Effort:** 3-4 hours
- **Risk:** Forecasts beyond ~6 months get unreliable; need to show widening confidence bands honestly.
- **Honest take:** Recommend cautiously. Add it but cap forecast horizons at 2 quarters and be loud about uncertainty in quarters 3-4.

### 2.4 — FX vs stock attribution (DEEPENS — for US stocks) — **BUILT (v1.1)**

For each US stock trade, split the AUD return into:

- "How much came from the stock moving"
- "How much came from the AUD/USD rate moving"

Why: a US stock can be flat in USD but you make/lose 5% in AUD purely from currency. You should know which bet you're actually making.

- **Effort:** 2 hours (data is already there — just expose it)
- **Risk:** None
- **Honest take:** Recommend. Surprisingly few apps do this.

### 2.5 — Simple portfolio-level risk view (DEEPENS)

If you currently hold (or hypothetically take) more than one position from the watchlist, show:

- Total AUD at risk if all stops trigger
- Concentration: % in any one sector / market
- Correlation between current holdings (high correlation = false diversification)

Why: TRADEON currently thinks one trade at a time. Real portfolios have multiple. Even three correlated positions is much riskier than three independent ones.

- **Effort:** 3-4 hours
- **Risk:** Requires you to enter your holdings (manual entry; tied to the trade journal #1.2)
- **Honest take:** Recommend if you take 3+ positions at a time.

---

## TIER 3 — Nice to have, lower priority

### 3.1 — Print-friendly Deep Dive PDF export

Generate a PDF of any Deep Dive page on demand. Useful if you like to keep a paper file per stock you've researched. Streamlit doesn't natively do this; would need a separate `weasyprint` or `reportlab` step.

- **Effort:** 4-5 hours
- **Honest take:** Skip unless you actually want paper. Browser Ctrl+P already does 80% of this.

### 3.2 — Watchlist starring + custom ordering

Mark some stocks as "favourites" and they pin to the top of the Dashboard. Custom-defined sub-lists ("My core picks", "Speculative").

- **Effort:** 2-3 hours
- **Honest take:** Skip. You only have 21 stocks; sorting columns already covers this.

### 3.3 — Dividend / ex-div date overlay

For ASX stocks especially, show upcoming ex-dividend dates and franking credits on the Deep Dive. yfinance provides this data.

- **Effort:** 2-3 hours
- **Risk:** Dividend data via yfinance can be delayed/stale.
- **Honest take:** Worth it for ASX large caps where franking matters.

### 3.4 — Sector heatmap

A grid showing all watchlist stocks coloured by current regime, grouped by sector. One-glance market mood.

- **Effort:** 1 hour
- **Honest take:** Marginal value above the Dashboard. Maybe combine with #1.1 (Today's Playbook).

### 3.5 — Backtest with custom watchlist (UPLOAD CSV)

Let the user upload a custom list of tickers and backtest TRADEON on them.

- **Effort:** 2 hours
- **Risk:** Random tickers may have insufficient data and crash modules. Need defensive handling.
- **Honest take:** Skip unless you want to research stocks beyond the curated 21.

### 3.6 — Mobile-first re-skin

Tighter layouts, bigger tap targets, swipe nav between pages. Streamlit is desktop-first by default.

- **Effort:** 6-8 hours of iteration
- **Honest take:** Streamlit will always be a desktop-first tool. If the tablet experience matters a lot, eventually move to a proper React/Next.js front-end (which was option D in the original plan).

---

## ABOUT BROKER INTEGRATION (the question you asked)

> "Can it do any links to brokers and stuff and how to buy stuff through this? Is that possible or is that too hard?"

There's a spectrum. Here's the honest reality.

### What's easy and safe (already in your reach)

- **Deep-link buttons** that open your broker's web app on the right symbol page. (Idea #1.3 above.)
- **Clipboard-copy order ticket** so you paste exact details into the broker. (Idea #1.4.)
- **Step-by-step text walkthrough** per broker. (Already in the app — `core/trade_walkthrough.py`.)

These three together remove most of the friction without removing your final-click control.

### What's possible but legally / technically risky

- **Direct API order placement** via broker APIs.
  - **Stake** has an unofficial API that some users reverse-engineered. **It is not approved for third-party use** and they can revoke your account access if detected. **Don't go there.**
  - **CommSec, Pearler, SelfWealth** — no public retail APIs at all.
  - **Interactive Brokers** has a real API (TWS/IBKR Gateway) and is the only Australian-accessible broker where TRADEON could actually place orders programmatically. But IBKR is overkill unless you're trading $50k+ portfolios.
  - **US-only:** Alpaca has a clean public API and accepts AU residents in some flows, but it's US stocks only.

If you eventually go with **IBKR** or **Alpaca**, TRADEON could in principle:
1. Submit your trade with a limit price and stop-loss attached
2. Pull back fill confirmations
3. Auto-update the trade journal (#1.2)

But this is the kind of feature that:
- Needs careful authentication (OAuth or API key in encrypted secrets)
- Should default to "dry run / paper trading" mode for the first 6 months
- Requires you to accept that a software bug could hit the wrong button

### My recommendation on broker integration

- **Now:** add #1.3 + #1.4 (deep-link button + clipboard-copy ticket). Two hours of work, zero risk, addresses 90% of the convenience gap.
- **Later (only if you start trading frequently):** consider an IBKR connection in dry-run mode for hands-off execution. Don't enable live trading until you've manually verified the system would have placed the orders correctly across at least 10 paper trades.
- **Never:** automated trading on Stake/CommSec/Pearler/SelfWealth via reverse-engineered APIs. The convenience is not worth the account-loss risk.

---

## What I'd build next, if you said "pick three"

The original "pick three" recommendation (#1.1, #1.2, #1.3+#1.4) is all built and in the live app. With 5 toggleable enhancements now also shipped, the next frontier is making the system more *autonomous* and more *opinionated about portfolio-level risk*. The new top-three list:

1. **#2.1 Signal-change notifications** (still TODO) — push or email when a stock flips WAIT → GO. The whole point of swing trading is "buy now, check back in a few months", so daily babysitting the app is unnecessary. The GitHub Actions cron + ntfy.sh combo would be the cleanest path. ~4-6h.
2. **#2.5 Portfolio-level risk view** (still TODO) — once you start running 3+ open positions from the Journal, "how correlated are they really?" matters more than any single-stock signal. ~3-4h.
3. **A new toggle: "GO needs a same-direction VIX move"** (idea, not yet specced) — only fire a GO if VIX has moved in the protective direction (down for longs) over the last 5 trading days. Adds a regime-momentum filter that complements toggle #2 (cross-asset confirmation) without overlap. ~2h.

After those, the next genuine accuracy frontier is **toggle #6: Bayesian model-averaging** — a smarter version of recency-weighted that incorporates uncertainty about the weights themselves. But the diminishing returns are real; recency-weighting already captures most of the easy lift.

---

## Things I'd explicitly NOT build

- **More forecasting models.** Five is already enough. A sixth model dilutes the ensemble without meaningfully improving it.
- **Sentiment scoring from social media or news.** You explicitly wanted to avoid news-derived signals. Don't break that promise.
- **Crypto.** Different beast, different math, different fee structure.
- **Day-trading features.** TRADEON is built for swing trades. Adding intraday support would compromise the core design.
- **Generic "AI commentary" generated by an LLM.** Adds words, removes precision. The numbers are the value.
- **Subscription / multi-user / login system.** It's your tool. Keep it personal.
- **Anything that requires consuming external predictions.** That principle is the soul of the project.

Restraint is a feature.
