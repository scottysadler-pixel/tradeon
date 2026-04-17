# TRADEON

A local Streamlit app that learns 20 years of price patterns for an Australian-tilted watchlist of prominent stocks, runs in-house forecasting models against itself to earn a per-stock trust grade, and only issues a "GO" signal when multi-model consensus, market regime, seasonal window and technical indicators all agree. All projections are computed locally from raw OHLCV - no external predictions are consumed.

This is **decision support, not financial advice.**

## What it does

1. Pulls 20 years of raw daily price data per stock (yfinance).
2. Runs an ensemble of forecasters (Prophet + Holt-Winters + ARIMA + naive baselines).
3. Detects current market regime (bull / bear / sideways) and only trusts forecasts trained on similar periods.
4. Finds each stock's best historical hold-window (e.g. "BHP gains avg 8.2% bought late Oct, sold late Feb, 73% hit rate").
5. Walk-forward backtests itself - earns trust grade A-F vs naive baselines, **net of broker fees and AU CGT**.
6. Issues GO signal only when ensemble + regime + seasonal window + technical confirmation all align.
7. Reports everything in AUD with broker-specific "how to actually place this trade" walkthroughs.

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

## Project layout

```text
TRADEON/
├── app.py                     # Streamlit landing page
├── pages/                     # Multi-page UI
├── core/                      # All brains live here (no Streamlit imports)
├── data_cache/                # Local Parquet cache (auto-created, gitignored)
└── tests/                     # Pytest suite
```

The `core/` package has zero UI dependencies, so it can be lifted into a FastAPI backend later if you want to upgrade to a hosted web app.

## How it actually works (plain English)

- **Trust grade A-F**: every refresh, the app pretends to be back in time, predicts forward, then compares to what really happened. The grade tells you whether to take this stock's next prediction seriously.
- **Default state is WAIT**: most days the dashboard will show no green lights. That is the point - the system protects you from low-quality trades.
- **GO signal**: comes with entry window, suggested exit date, stop-loss, expected AUD return after fees and tax.
- **All from raw prices**: no external predictions. The only thing entering the system is historical OHLCV data.

## Honest limitations

- Statistical models cannot predict shocks (COVID, GFC, earnings surprises). The trust grade will visibly drop after such events - that is the system working correctly.
- Past performance does NOT guarantee future results.
- Short holds (under 12 months) lose the AU 50% CGT discount. The app shows you both pre- and post-tax outcomes so you can decide if the trade still beats a 12-month hold after tax.
- Expect mostly grey "WAIT" status on the dashboard. Possibly only 1-3 active GO signals at a time across the watchlist.

## Backup workflow

The full project (excluding the regenerable `data_cache/`) is git-tracked. Push to a private GitHub repo as your real backup:

```powershell
git remote add origin git@github.com:YOUR_USERNAME/TRADEON.git
git push -u origin main
```

Optionally also point a Google Drive folder at the project root for a second copy.

## Disclaimer

TRADEON produces statistical projections based on historical price data. It is not licensed financial advice. You are solely responsible for your investment decisions. Past performance does not guarantee future results. The author accepts no liability for losses.
