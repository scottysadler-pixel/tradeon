# TRADEON

A local Streamlit app that learns 20 years of price patterns for an Australian-tilted watchlist of prominent stocks, runs in-house forecasting models against itself to earn a per-stock trust grade, and only issues a "GO" signal when multi-model consensus, market regime, seasonal window and technical indicators all agree. All projections are computed locally from raw OHLCV — no external predictions are consumed.

This is **decision support, not financial advice.**

## What it does

1. Pulls 20 years of raw daily price data per stock (yfinance, bundled in the repo and refreshed nightly by a GitHub Action).
2. Runs an ensemble of forecasters (Prophet + Holt-Winters + ARIMA + naive baselines).
3. Detects current market regime (bull / bear / sideways) and only trusts forecasts trained on similar periods.
4. Finds each stock's best historical hold-window (e.g. "BHP gains avg 8.2% bought late Oct, sold late Feb, 73% hit rate").
5. Walk-forward backtests itself — earns trust grade A-F vs naive baselines, **net of broker fees and AU CGT**.
6. Issues GO signal only when ensemble + regime + seasonal window + technical confirmation all align.
7. Reports everything in AUD with broker-specific "how to actually place this trade" walkthroughs.

## Five opt-in enhancements (Strategy Lab)

The default behaviour is the v1 baseline. Five additional toggles let you sharpen forecasts or add safety filters — each one earns its keep individually before you turn it on globally:

| # | Toggle | What it does |
|---|--------|--------------|
| 1 | **GARCH volatility** | Forecasts volatility for the next 90 days; shrinks position size when a storm is expected, grows it when calm. |
| 2 | **Cross-asset confirmation** | Blocks a single-stock GO if the parent index (S&P 500 / ASX 200) is in a bear regime or VIX > 30. |
| 3 | **Regime-stratified trust grade** | Grades the model only on quarters whose start-regime matches today's, instead of all-history average. |
| 4 | **Recency-weighted ensemble** *(v1.3)* | Re-weights prophet/holt-winters/arima by which has been most accurate over the last 5 quarterly forecasts. |
| 5 | **Drawdown circuit-breaker** *(v1.3)* | Forces any GO to WAIT if the stock has fallen more than 15% from its peak in the last 30 trading days. |

All toggles default to OFF. The Strategy Lab page lets you flip them on, run an honest ON-vs-OFF backtest comparison per stock, and apply the combo globally only when it consistently helps.

See **[USER_GUIDE.md § 1.5](./USER_GUIDE.md#15-how-it-all-fits-together)** for a full mental model of how toggles plug into the pipeline.

## Quick start

```powershell
# 1. Create a virtual environment (Python 3.11 or 3.12 recommended for full Prophet support)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Optional: install Prophet for best accuracy on big-tech names
pip install prophet

# 4. Launch the app
streamlit run app.py
```

The app opens in your browser at <http://localhost:8501>.

For repeatable iPad / tablet starts, do a one-time warm pass:

1. Open **Data Tools**.
2. Open the **Mobile speed profile** section (in the app sidebar), enable it only if you want lower CPU use.
3. Click **Pre-warm raw price cache now**.
4. Click **Pre-compute watchlist analysis now**.

After that warm pass, page transitions are much faster because Dashboard and Forward Outlook render cached rows immediately.
Data Tools is also where you build, validate, download, and import cache packs.
Cache-pack controls are no longer shown in the home sidebar.

## Project layout

```text
TRADEON/
├── app.py                     # Streamlit landing page
├── pages/                     # Multi-page UI
│   ├── 0_Data_Tools.py         # Cache pre-warm + cache-pack controls
│   ├── 1_Dashboard.py         # Watchlist overview + trust grades
│   ├── 2_Deep_Dive.py         # Single-stock 20-year analysis
│   ├── 3_Backtest_Lab.py      # Interactive prediction-vs-actual playground
│   ├── 4_Forward_Outlook.py   # Live GO signals only
│   ├── 5_Watchlist.py         # Watchlist + recommender + cache mgmt
│   ├── 6_Learn.py             # Plain-English education
│   ├── 7_Help.py              # In-app version of USER_GUIDE.md
│   ├── 8_Journal.py           # Journal and scenario notes
│   └── 9_Strategy_Lab.py      # Toggle comparisons and global presets
├── core/                      # All brains live here (no Streamlit imports)
│   ├── cache_pack.py          # Build/validate/restore portable cache bundles
│   ├── pipeline_cache.py      # Disk cache for analyse_one() output
│   └── backtest_cache.py      # Disk cache for Backtest Lab
├── data_cache/                # Local Parquet cache (auto-created, gitignored)
├── scripts/                   # Maintenance scripts (refresh cache + refresh pipeline)
├── .streamlit/
│   └── config.toml            # Streamlit runtime + folderWatchBlacklist
├── tests/
└── requirements.txt
```

The `core/` package has zero UI dependencies, so it can be lifted into a FastAPI backend later if you want to upgrade to a hosted web app.

## How it actually works (plain English)

- **Trust grade A-F**: every refresh, the app pretends to be back in time, predicts forward, then compares to what really happened. The grade tells you whether to take this stock's next prediction seriously.
- **Default state is WAIT**: most days the dashboard will show no green lights. That is the point — the system protects you from low-quality trades.
- **GO signal**: comes with entry window, suggested exit date, stop-loss, expected AUD return after fees and tax.
- **All from raw prices**: no external predictions. The only thing entering the system is historical OHLCV data.
- **Toggles never lower the bar.** Enhancements either sharpen the forecast or add extra safety filters; they never make a GO easier to fire than vanilla.

For the full pipeline diagram and the role of each toggle, see [USER_GUIDE.md § 1.5](./USER_GUIDE.md#15-how-it-all-fits-together).

## Honest limitations

- Statistical models cannot predict shocks (COVID, GFC, earnings surprises). The trust grade will visibly drop after such events - that is the system working correctly.
- Past performance does NOT guarantee future results.
- Short holds (under 12 months) lose the AU 50% CGT discount. The app shows you both pre- and post-tax outcomes so you can decide if the trade still beats a 12-month hold after tax.
- Expect mostly grey "WAIT" status on the dashboard. Possibly only 1-3 active GO signals at a time across the watchlist.

## Backup + tablet access

The full project (excluding the regenerable `data_cache/`) is git-tracked. Push to a private GitHub repo for both backup and tablet access:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/tradeon.git
git push -u origin main
```

To then run TRADEON from your tablet, phone or any other browser (no laptop required), follow the step-by-step in **[DEPLOY.md](./DEPLOY.md)** - it deploys the app for free to Streamlit Community Cloud, auto-redeploys on every push, and supports Google-login access control.

Optionally also point a Google Drive folder at the project root for a second copy.

## Documentation

- **[USER_GUIDE.md](./USER_GUIDE.md)** — plain-English user manual (also available in-app under the **Help** page; printable via Ctrl+P).
  - § 1.5 *How it all fits together* — the mental model with a pipeline diagram
  - § 6 *Acting on a GO signal* — the disciplined-trade checklist
  - § 6.5 *The Strategy Lab* — what each toggle does
  - § 6.6 *Recommended toggle starter packs* — three ready-made combinations
  - § 6.7 *Reading the diagnostic captions* — how to read the new Forward Outlook annotations
  - § 2.8 *Tablet-first first-run flow* — warming cache and using Data Tools on iPad
- **[DOCS.md](./DOCS.md)** — technical reference: architecture, trust-grade math, the full data-flow diagram with all five toggle stages, every module explained
- **[DEPLOY.md](./DEPLOY.md)** — step-by-step deploy to Streamlit Community Cloud for tablet access
- **[IMPROVEMENTS.md](./IMPROVEMENTS.md)** — prioritised list of future enhancements (with deliberate restraint about what NOT to build), and which ones have already been built

## Disclaimer

TRADEON produces statistical projections based on historical price data. It is not licensed financial advice. You are solely responsible for your investment decisions. Past performance does not guarantee future results. The author accepts no liability for losses.
