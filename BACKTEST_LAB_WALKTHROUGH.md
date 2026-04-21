# Backtest Lab Walkthrough - Practice Testing Without Risk

**Purpose:** Learn to use the Backtest Lab to see "what would have happened" without logging any trades.

---

## Example 1: Testing a GO Signal Before Acting

**Scenario:** You see CBA.AX has a GO signal on the Dashboard. You want to test if this kind of signal has worked historically before placing a real trade.

### Steps:

1. **Go to Backtest Lab page** (click in left sidebar)

2. **Select stock:** Choose `CBA.AX` from dropdown

3. **Select model:** Choose `ensemble` (this is what TRADEON uses for GO signals)

4. **Select horizon:** Choose `90 days` (typical hold period)

5. **Select history range:** Choose `Last 5 years` (faster, more relevant)

6. **Click "Run backtest"**

### What to look for:

**Chart:**
- Green line = Actual returns
- Blue line = Model predictions
- Do they track together? Or are they all over the place?

**Metrics panel:**
- **MAPE:** Is it < 10%? (Good) or > 25%? (Poor)
- **Directional accuracy:** Is it > 55%? (Meaningful)
- **Paper-trade net AUD:** Would you have made money trading this historically?

**Verdict:**
- If MAPE < 12%, directional > 60%, paper-trade positive → trust the signal
- If MAPE > 20%, directional < 50% → be skeptical

---

## Example 2: Comparing Models (Which One Works Best?)

**Scenario:** You're curious if `prophet` or `arima` works better for WES.AX.

### Steps:

1. **Select WES.AX**
2. **Run with model = `prophet`, horizon = 90 days**
3. **Note the Paper-trade net AUD and MAPE**
4. **Change model to `arima`, click Run again**
5. **Compare the two results**

### Interpretation:

| Model | Paper-trade net | MAPE | Winner |
|-------|----------------|------|--------|
| Prophet | +$2,450 | 8.2% | ✓ |
| Arima | +$1,820 | 11.5% | |

**Conclusion:** Prophet performs better for WES.AX historically. But TRADEON uses `ensemble` (average of all three), which smooths out the noise.

---

## Example 3: "What If I Had..." Scenario

**Scenario:** It's April 2026. You want to know: "What if I had bought BHP.AX in October 2025 for a 90-day hold?"

### Steps:

1. **Select BHP.AX**
2. **Model: ensemble, Horizon: 90 days**
3. **History range: All available** (so you get data through 2025)
4. **Click Run**
5. **Look at the chart** - find the Oct 2025 point
6. **Read the prediction vs actual**

### What the chart shows:

- The **blue line** (prediction) at Oct 2025 shows what TRADEON would have predicted
- The **green line** (actual) at Jan 2026 shows what really happened
- **Gap between them** = prediction error

If prediction said +7% and actual was +9%, TRADEON underestimated by 2 percentage points.

---

## Example 4: Trust Grade Deep Dive

**Scenario:** Forward Outlook shows a GO for NVDA, but you're nervous about US tech. Use the Lab to understand why it has the trust grade it does.

### Steps:

1. **Select NVDA**
2. **Model: ensemble, Horizon: 90 days, History: All available**
3. **Run**
4. **Scroll through the chart** - look at 2020-2024 period especially
5. **Check CI coverage** - are actuals mostly falling inside the prediction bands?

### Red flags:

- **Predictions consistently miss by >20%** → model doesn't understand this stock
- **Predictions great 2010-2020, terrible 2021-2024** → recent behavior changed
- **Big gaps during COVID crash** → model struggles with black swans (expected)

### Green flags:

- **Predictions track actuals closely most of the time**
- **When wrong, the magnitude isn't huge**
- **Paper-trade net is solidly positive**

---

## Example 5: Horizon Testing (30 vs 90 vs 180 days)

**Scenario:** You want to hold for 6 months instead of 3. Does the model work better or worse at 180-day horizons?

### Steps:

1. **Pick a stock you're interested in** (e.g., ANZ.AX)
2. **Run with horizon = 30 days**
3. **Note MAPE and directional accuracy**
4. **Run with horizon = 90 days**
5. **Run with horizon = 180 days**
6. **Compare**

### Typical pattern:

| Horizon | MAPE | Directional | Why |
|---------|------|-------------|-----|
| 30 days | 5.2% | 58% | Short-term noise is hard to predict |
| 90 days | 8.7% | 67% | Sweet spot - seasonal patterns show up |
| 180 days | 14.3% | 62% | Too long - more unknowns accumulate |

**TRADEON uses 90 days** as the default because that's where the signal-to-noise ratio is best for most stocks.

---

## Practice Workflow: Use Backtest Lab Before Every GO Signal

**Recommended process:**

1. See a GO signal on Dashboard or Forward Outlook
2. Before placing the trade:
   - Open **Backtest Lab**
   - Run `ensemble, 90 days, Last 5 years` for that stock
   - Check: MAPE < 12%? Directional > 60%? Paper-trade positive?
3. If yes → place the trade with confidence
4. If no → be more cautious, or skip entirely

This gives you a "reality check" before committing real money.

---

## Common Questions

**Q: Why doesn't the chart show today's date?**
A: Backtest Lab shows *historical* predictions vs actuals. It can't show "what will happen in the future" (only Forward Outlook attempts that). The most recent point is the most recent *completed* 90-day window.

**Q: The paper-trade net is negative. Does that mean don't trade this stock?**
A: Not necessarily. It means the *model* hasn't historically beaten a simple "do nothing" baseline for this stock. Check the Trust Grade on the Dashboard - if it's D or F, then yes, avoid. If it's B or C, the model is marginal but not useless.

**Q: Which is more important - MAPE or directional accuracy?**
A: **Directional accuracy** for short-term trading. You care more about "was it going up or down" than "was it +7.2% or +9.4%". But both matter.

**Q: Can I use this to backtest Strategy Lab toggles?**
A: Not directly. The Backtest Lab always uses vanilla settings. Use the **Strategy Lab** page itself to compare ON vs OFF for toggles.

**Q: The first run took 30 seconds. Why?**
A: First run has to compute all the historical folds. Subsequent runs (even after closing the browser) are cached on disk for ~1 week, so they're instant.

---

## Summary: Backtest Lab = Your "What If" Machine

- **Before a GO signal:** Check if the model has a good track record for this stock
- **After a missed opportunity:** See what would have happened if you'd acted
- **For learning:** Compare models, horizons, stocks to build intuition
- **No risk:** Everything is historical - you're not logging any trades

**Key takeaway:** If a stock consistently shows MAPE < 10% and directional > 60% in the Backtest Lab, and the Trust Grade is A or B, you can trust GO signals for that stock with high confidence.

---

**Next steps:**
1. Open Backtest Lab now
2. Pick a stock showing a GO signal (or one you're curious about)
3. Run `ensemble, 90 days, Last 5 years`
4. Spend 5 minutes looking at the chart and metrics
5. You'll immediately understand why Trust Grades exist

---

*This is a learning tool, not a guarantee. Past performance doesn't predict future results. But it's the best objective measure we have.*
