# TRADEON Quick Start Guide

**Version:** 1.6 | **Date:** April 2026

---

## What TRADEON Does (10 seconds)

Analyzes 27 stocks using 20 years of history. Issues **GO** signals when multiple factors align for a profitable 30-90 day trade. Most days = **WAIT** (that's correct behavior).

---

## The Pages - What Each One Does

### 🏠 **Home**
- **Today's Playbook** - fastest way to see if there are any GO signals right now
- **Watchlist mood** - is the overall market bullish/bearish/sideways?
- **Engine status** - cache health, when data was last refreshed

**When to use:** Start here every session. If no GO signals, you're done for the day.

---

### 📊 **Dashboard**
- Table view of all 27 stocks
- Shows: Trust grade, Regime, Signal (GO/WAIT/AVOID), Expected return
- Sort by Trust grade to see your most reliable stocks first

**When to use:** 
- Daily check-in (once per day is plenty)
- To see the full watchlist at a glance
- To find which stocks are closest to a GO signal

**First load takes:** 3-5 minutes on fresh deploy (warming cache). Subsequent visits: instant.

---

### 🔍 **Deep Dive**
- Full report on ONE stock
- 20-year price chart with bear periods shaded
- Best historical hold-windows (buy month → sell month)
- Hypothetical trade calculator: "What if I bought $1000 on date X?"
- Backtest summary showing model accuracy

**When to use:**
- Before acting on a GO signal (understand the stock's history)
- To sanity-check a hold-window suggestion
- When curious about a specific stock

---

### 🧪 **Backtest Lab**
- Shows "predicted vs actual" charts for any stock/model/horizon
- Tests how well the model performed historically
- Compare `ensemble` (what TRADEON uses) vs `naive` (simple baseline)

**When to use:**
- To build trust in the system (see predictions vs reality)
- To understand why a stock has the trust grade it does
- To check if a specific model (prophet/holt-winters/arima) works better for a stock

**Key metrics to watch:**
- **MAPE** < 10% = good, > 25% = guessing
- **Directional accuracy** > 55% = meaningful
- **Paper-trade net AUD** = would you have made money?

---

### 🎯 **Forward Outlook**
- Shows only GO signals (empty most days = normal)
- Full trade plan: entry price, exit date, stop-loss, position size
- Clipboard order ticket (copy-paste ready)
- Links to open your broker and Yahoo Finance chart

**When to use:**
- When Dashboard or Home shows a GO signal
- To get the specific numbers you need to place a trade

**Pre-trade checklist:**
- Trust grade A or B? ✓
- Regime not bear? ✓
- Hit rate > 65%? ✓
- Expected return > 5% net? ✓
- Can afford to lose this amount? ✓

---

### 📓 **Trade Journal**
- Log REAL trades you actually placed
- Calculates net AUD after fees and AU CGT
- Tracks your hit rate vs TRADEON's predictions
- Shows if trading against WAIT signals helps or hurts

**When to use:**
- After you BUY: log the entry immediately
- After you SELL: close the trade
- Weekly: download a backup CSV (data is ephemeral on Streamlit Cloud)

**Not for practice trades** - this is your real trading record.

---

### 🔬 **Strategy Lab**
- Test if turning ON enhancements actually helps
- Compare metrics ON vs OFF before deciding
- Apply globally once you find a combo that works

**The 5 toggles:**
1. **GARCH volatility** - smarter position sizing
2. **Cross-asset confirmation** - blocks GO when overall market is hostile
3. **Regime-stratified trust** - grades model only on similar conditions
4. **Recency-weighted ensemble** - favors whichever sub-model is hot lately
5. **Drawdown circuit-breaker** - blocks GO if stock is falling fast

**How to use:**
1. Pick a stock
2. Flip ONE toggle ON
3. Click "Run comparison"
4. Did Trust Score improve? Try on 2-3 more stocks
5. If consistent lift, click "Apply globally"

**Default = all OFF** - that's the baseline you've been using.

---

### 🛠️ **Data Tools**
- Pre-warm caches (makes page switches faster on iPad)
- Build/import cache packs (portable zip for other devices)
- Mobile speed profile (caps workers/folds for weaker devices)

**When to use:**
- First thing in a new session on iPad
- Before traveling (export cache pack, restore on other device)
- If pages feel slow

**iPad tip:** Cache-pack zip opens as attachment. Close it to return to app, import later if needed.

---

## Typical Daily Workflow

### Quick check (2 minutes)
1. Open app → **Home** page
2. Read "Today's Playbook"
3. If no GO signals: done for the day
4. If GO signal: continue below

### Acting on a GO signal (15 minutes)
1. **Dashboard** → confirm signal still shows GO
2. **Deep Dive** → review stock's history and hold-window hit rate
3. **Forward Outlook** → get trade plan details
4. Use pre-trade checklist (see Forward Outlook section above)
5. Place trade in your broker
6. **Trade Journal** → log the entry immediately

### Closing a trade
1. When exit date arrives or stop-loss hits: sell in your broker
2. **Trade Journal** → log the exit
3. Review net AUD after tax

### Weekly maintenance
1. **Trade Journal** → download CSV backup
2. Check **Home** → "Engine status" to see cache health

---

## Paper Trading Workaround

**The Journal is for real trades only.** For practice:

**Option 1: Use Journal with "PAPER" flag**
- Log trades normally
- Put `PAPER TRADE` in the Notes field
- Filter mentally when reviewing performance
- Download CSV, delete paper trades in Excel, re-import when ready for real trading

**Option 2: Use Backtest Lab**
- Pick a stock and recent date range
- See what TRADEON would have predicted
- Compare to actual outcome
- This is "what would have happened" testing

**Option 3: Forward Outlook + spreadsheet**
- When you see a GO signal, screenshot or note the details
- Track it in your own spreadsheet without placing the trade
- Check back at the exit date to see if it would have worked

---

## Strategy Lab Quick Reference

| Toggle | What it does | When to use |
|--------|--------------|-------------|
| **GARCH** | Adjusts position size based on volatility forecast | Always useful; no downside |
| **Macro confirm** | Blocks GO if overall market is bearish | Defensive; fewer signals but safer |
| **Regime grade** | Grades only on similar market conditions | When current regime is unusual |
| **Recency weight** | Favors best-performing sub-model lately | When recent behavior changed |
| **Drawdown brake** | Blocks GO if stock fell >15% in 30 days | Defensive; avoids falling knives |

**Starter pack recommendation:**
- Defensive: Macro confirm + Drawdown brake
- Performance: Recency weight + GARCH
- All-in: All four above (skip Regime grade unless needed)

---

## Key Metrics Explained

| Metric | What it means | Good = | Bad = |
|--------|---------------|--------|-------|
| **Trust grade** | Historical profitability after fees+tax | A, B | D, F |
| **Hit rate** | % of trades that were profitable | >65% | <50% |
| **MAPE** | Average prediction error (%) | <10% | >25% |
| **Directional accuracy** | % where up/down was called correctly | >55% | <50% |
| **Pattern strength** | How repeatable seasonal cycles are | >0.5 | <0.3 |
| **Expected return** | Net AUD % gain after fees+tax | >5% | <2% |

---

## Troubleshooting One-Liners

| Problem | Fix |
|---------|-----|
| Dashboard shows all WAIT | Normal. GO signals are rare (few per quarter) |
| First load very slow | Expected (3-5 min). Use Data Tools to pre-warm |
| iPad downloads open full-screen | Close preview, return to app. It's saved as attachment |
| Trust grades suddenly dropped | Recent market shock. Wait a few weeks |
| Strategy Lab shows error | Click "Clear cached settings + cache" at top of page |
| New stocks not showing | Hard refresh browser (Ctrl+Shift+R) |

---

## One-Page Mental Model

```
Daily prices (20 years)
    ↓
Convert to AUD
    ↓
┌────────────────────────────────────┐
│  REGIME     FORECAST      EVIDENCE │
│  (HMM)      (Ensemble)    (Techs)  │
└───────────┬────────────────────────┘
            ↓
    TRUST GRADE (A-F)
    (historical accuracy)
            ↓
    ┌─── Decision AND-gate ────┐
    │  Trust ≥ B               │
    │  + Regime OK             │
    │  + Hold-window match     │
    │  + Positive expected     │
    │  + Technical confirm     │
    │  + No earnings window    │
    └──────────┬───────────────┘
               ↓
        GO / WAIT / AVOID
               ↓
    (Strategy Lab toggles
     can add extra filters here)
               ↓
        Final signal
```

---

## Resources

- **In-app Help**: Click "Help" in sidebar → full USER_GUIDE.md
- **In-app Learn**: Click "Learn" in sidebar → quick overview
- **Full docs**: See `USER_GUIDE.md`, `DOCS.md` in the repo

---

## Remember

- **WAIT is not a bug.** It's the correct default.
- **Check once per day** - hourly checks add no value for 30-90 day swings.
- **Trust grade is king.** Only trade A/B stocks.
- **Backtest before believing.** Use Backtest Lab to build confidence.
- **Paper trade first** (use workarounds above) if new to this.
- **Journal backup weekly.** Streamlit Cloud can wipe your data.

---

**This is decision support, not financial advice. You are responsible for your trades.**
