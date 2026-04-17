# TRADEON — Technical Documentation

Reference document for what TRADEON is, how it's built, and how each piece of the engine works. For practical "how do I use this app" guidance, read [USER_GUIDE.md](./USER_GUIDE.md). For deployment instructions read [DEPLOY.md](./DEPLOY.md).

---

## 1. What TRADEON is

TRADEON is a self-validating short-to-medium-term stock outlook engine for an Australian retail trader. It analyses 20 years of raw daily price history for a hand-picked watchlist of large-cap ASX and US stocks, runs in-house statistical forecasts, and grades itself on how accurate those forecasts have been historically. It then issues conservative `GO`, `WAIT`, or `AVOID` signals only when several independent indicators agree.

**Core principles:**

- **No external predictions consumed.** The only data ingested is raw OHLCV (Open, High, Low, Close, Volume) from yfinance. No analyst targets, no broker recommendations, no news scrapers, no sentiment APIs.
- **Default state is WAIT.** Most days, most stocks show no green light. That is the system protecting you, not failing.
- **Honesty over confidence.** Every model's output is graded against a naive baseline. If the model can't beat "tomorrow = today" net of fees and tax, it is silenced for that stock.
- **AUD-native.** All returns and trade outcomes report in Australian dollars, with historical AUD/USD conversion applied to US-listed names.
- **AU-tax-aware.** Backtests apply realistic broker fees (CommSec, Stake, Pearler, SelfWealth) and the 50% Capital Gains Tax discount when applicable.

---

## 2. Architecture

```text
TRADEON/
├── app.py                     ← Streamlit landing page
├── ui_helpers.py              ← Shared UI widgets, badges, formatters
├── pages/                     ← Multi-page Streamlit UI
│   ├── 1_Dashboard.py         ← Watchlist overview + trust grades
│   ├── 2_Deep_Dive.py         ← Single-stock 20-year analysis
│   ├── 3_Backtest_Lab.py      ← Interactive prediction-vs-actual playground
│   ├── 4_Forward_Outlook.py   ← Live GO signals only
│   ├── 5_Watchlist.py         ← Watchlist + recommender + cache management
│   ├── 6_Learn.py             ← Plain-English education
│   └── 7_Help.py              ← In-app version of USER_GUIDE.md
├── core/                      ← All business logic — zero Streamlit imports
│   ├── tickers.py             ← The 21-stock watchlist
│   ├── glossary.py            ← Definitions for tooltips & education
│   ├── data.py                ← yfinance fetch + Parquet cache
│   ├── fx.py                  ← AUD/USD conversion
│   ├── costs.py               ← AU broker fees + CGT logic
│   ├── analysis.py            ← Stats, seasonality, EOFY pattern
│   ├── regime.py              ← HMM bull/bear/sideways detector
│   ├── technicals.py          ← RSI, MACD, Bollinger Bands
│   ├── hold_window.py         ← Best buy-month / sell-month finder
│   ├── earnings_proxy.py      ← Volatility-cluster detection
│   ├── stops.py               ← Drawdown-aware stop-loss suggester
│   ├── position_size.py       ← Volatility-adjusted sizing
│   ├── correlations.py        ← Watchlist co-movement & divergences
│   ├── forecast.py            ← Naive, seasonal, Holt-Winters, ARIMA, Prophet, ensemble
│   ├── backtest.py            ← Walk-forward backtest + trust-grade calculator
│   ├── signals.py             ← The GO / WAIT / AVOID decider
│   ├── recommendations.py     ← In-watchlist suggester
│   └── trade_walkthrough.py   ← Broker-specific "how to actually place this trade"
├── tests/                     ← Synthetic + live pytest suites
├── data_cache/                ← Local Parquet cache (gitignored)
├── .streamlit/config.toml     ← Theme + cloud-friendly server config
├── runtime.txt                ← Pins Python 3.11 for Streamlit Cloud
└── requirements.txt           ← All dependencies
```

The `core/` package has **zero UI dependencies**. It can be lifted into a FastAPI backend, a CLI, or a notebook with no rework. This is by design and protects the upgrade path to a full web app later.

---

## 3. Data flow (top to bottom)

```text
yfinance (raw OHLCV)
    ↓
core/data.py — fetch + Parquet cache (data_cache/<symbol>_adj.parquet)
    ↓
core/fx.py — convert USD prices to AUD using AUDUSD=X history
    ↓
┌─────────────────────────────────────────────────────────────┐
│  Per-stock pipeline (cached for 1 hour)                     │
│                                                             │
│  core/analysis.py  →  CAGR, vol, drawdown, seasonality      │
│  core/regime.py    →  current bull/bear/sideways            │
│  core/technicals.py →  RSI, MACD, Bollinger snapshot        │
│  core/hold_window.py →  best historical buy/sell months     │
│  core/earnings_proxy.py → upcoming volatility windows       │
│  core/stops.py     →  recommended stop-loss level           │
│  core/correlations.py → divergence flags vs watchlist       │
│  core/forecast.py  →  ensemble forward-looking forecast     │
│  core/backtest.py  →  walk-forward back-check + trust grade │
│  core/position_size.py → vol-adjusted AUD position size     │
│  core/costs.py     →  apply broker fees + CGT to all maths  │
│  core/signals.py   →  combine everything → GO/WAIT/AVOID    │
└─────────────────────────────────────────────────────────────┘
    ↓
core/trade_walkthrough.py → broker-specific instructions
    ↓
Streamlit UI (pages/) → human-readable output
```

---

## 4. The trust grade — how it is computed

The trust grade (A through F) is the single most important number TRADEON produces. It says "how much should I trust this stock's next prediction?"

### 4.1 Walk-forward backtest

Implemented in `core/backtest.py:backtest_model`.

For each model (naive, seasonal-naive, Holt-Winters, ARIMA, Prophet, ensemble):

1. Slice the 20-year history into ~10 sequential **folds**.
2. For each fold, train ONLY on data available before the fold's start date.
3. Predict the next `horizon_days` (default 90) of prices.
4. When the fold's end date arrives, compare prediction to what really happened.
5. Apply the user's broker fees and AU CGT logic to compute the AUD return you would have actually pocketed.
6. Record metrics:
   - **MAPE** (Mean Absolute Percentage Error) — average size of the prediction error
   - **Directional accuracy** — what fraction of the time the predicted direction was right
   - **CI coverage** — what fraction of actuals fell within the model's stated confidence interval
   - **Paper-trade net AUD return** — what you would have actually made/lost trading on every signal

### 4.2 The honest twist

A naive baseline (`tomorrow = today`) is also backtested. If the chosen model can't beat this naive baseline net of fees and tax, the model is considered useless for that stock.

When the naive baseline produces a "no-call" prediction (a tiny absolute price change under 0.5%), it is scored as 0.5 (a coin flip) for directional accuracy rather than 0. This makes the comparison fair — penalising "no opinion" as wrong would unfairly inflate the model's apparent edge.

### 4.3 Grade letter

`core/backtest.py:trust_grade` combines the metrics into a composite score:

| Grade | Meaning |
|-------|---------|
| **A** | Beats naive comfortably on multiple metrics, directional accuracy >55%, positive net AUD return |
| **B** | Beats naive on most metrics, marginally profitable |
| **C** | Roughly matches naive — nothing learned, nothing lost |
| **D** | Underperforms naive on most metrics |
| **F** | Materially worse than naive — actively misleading |

A grade of **C or better** is the minimum bar before the signals decider will consider issuing a `GO` signal for that stock.

---

## 5. The GO / WAIT / AVOID decider

Implemented in `core/signals.py:decide`. To return `GO`, ALL of the following must be true:

1. **Trust grade is A or B** (model is reliable for this stock)
2. **Current regime is bull or sideways** (not bear)
3. **A historical hold-window applies right now** (e.g. "BHP from late Oct to late Feb has gained 8% on average with 73% hit rate")
4. **The ensemble forecast lift is materially positive** (after fees + CGT, in AUD)
5. **At least one technical confirmation** (RSI not overbought, MACD positive, price below Bollinger upper band)
6. **No earnings volatility window** is active (we don't want to open a trade right before an earnings surprise)
7. **No correlation divergence flag** suggests the stock is behaving anomalously vs its peers

If any condition fails, the result is `WAIT`. If the regime is `bear` AND the trust grade is poor, the result is `AVOID`.

This conservative AND-gate is intentional. Most days, most stocks return `WAIT`. That is the system working correctly.

---

## 6. Models in the forecast ensemble

| Model | Purpose | Strength |
|-------|---------|----------|
| **Naive** (`naive_forecast`) | Baseline: predict tomorrow = today | The bar all other models must clear |
| **Seasonal-naive** (`seasonal_naive_forecast`) | Predict same as 1 year ago | Catches strong seasonality |
| **Holt-Winters** (`holt_winters_forecast`) | Triple exponential smoothing | Handles trend + seasonality |
| **ARIMA** (`arima_forecast`) | AutoRegressive Integrated Moving Average | Standard time-series workhorse |
| **Prophet** (`prophet_forecast`, optional) | Meta's additive model | Strong on big-tech with structured seasonality |
| **Ensemble** (`ensemble_forecast`) | Weighted average of the above | Combines complementary strengths |

The ensemble's weights are NOT static. Each model's recent backtest accuracy (MAPE) is converted into a weight via `core/backtest.py:model_weights_from_backtest`, so models that have been doing well on a given stock get more say.

If Prophet is unavailable (e.g. on Python 3.14 before wheels arrive), the ensemble silently drops to Holt-Winters + ARIMA. The app continues to work with slightly reduced accuracy on big-tech names. On Streamlit Cloud, Python 3.11 is pinned via `runtime.txt` so Prophet installs automatically.

---

## 7. Costs and tax (AU-specific)

`core/costs.py` models four real Australian brokers:

| Broker | Per-trade fee model |
|--------|---------------------|
| **CommSec** | $10 flat (under $1k); $19.95 for $1k-$10k; 0.11% above |
| **Stake** | A$3 flat for ASX; US$3 flat for US |
| **Pearler** | $6.50 flat ASX; US$6.50 flat US |
| **SelfWealth** | $9.50 flat (any size) |

Capital Gains Tax (`cgt_on_gain`):

- Default marginal rate: 32.5% (modify in `core/costs.py:DEFAULT_MARGINAL_RATE`)
- Holdings under 365 days: full marginal rate applies
- Holdings 365 days+: **50% CGT discount** applies (taxable gain halved)

Every backtest paper-trade result and every Forward Outlook return projection is **net of fees and tax**. The Deep Dive page also shows the pre-tax vs post-tax difference so you can see how much of the alpha disappears.

---

## 8. Data caching

Two layers:

| Layer | Location | TTL | Purpose |
|-------|----------|-----|---------|
| **Raw OHLCV** | `data_cache/*.parquet` | 12 hours | Avoid hammering yfinance |
| **Pipeline output** | Streamlit memory (`@st.cache_data`) | 1 hour | Avoid re-running heavy backtests |

`core/data.py:_resolve_cache_dir` chooses a writable directory in this order:
1. `$TRADEON_CACHE_DIR` env var if set
2. `<repo_root>/data_cache`
3. System tempdir

This makes the app robust on Streamlit Cloud (where the project dir is writable but ephemeral) and on more locked-down hosts (where only `/tmp` may be writable).

The disk cache is invalidated by `core/data.py:clear_cache(symbol=None)` (which is exposed via the Watchlist page). Pipeline output cache clears automatically on app restart or after 1 hour idle.

---

## 9. Tests

| File | Type | What it covers |
|------|------|----------------|
| `tests/test_smoke.py` | Synthetic data | Every core module + end-to-end signal decider on fake price series |
| `tests/test_live.py` | Real yfinance data | MSFT and BHP.AX through the full pipeline |

Run all tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Smoke tests should always pass. Live tests need internet and may flake if Yahoo throttles or if data feeds change schemas.

---

## 10. Configuration knobs

Most behaviour is parameterised. Common things to tweak:

| What | Where |
|------|-------|
| Watchlist composition | `core/tickers.py:WATCHLIST` |
| Default lookback years | `core/data.py:DEFAULT_LOOKBACK_YEARS` |
| Cache TTL | `core/data.py:CACHE_TTL_HOURS` |
| Backtest horizon | `core/backtest.py` (default 90 days) |
| GO signal thresholds | `core/signals.py:decide` |
| AU CGT rate | `core/costs.py:DEFAULT_MARGINAL_RATE` |
| Broker fee profiles | `core/costs.py:BROKERS` |
| Ensemble model weights | `core/backtest.py:model_weights_from_backtest` |
| Theme colours | `.streamlit/config.toml` |

---

## 11. The page-by-page UI map

| Page | What it shows |
|------|---------------|
| **Landing (`app.py`)** | **Today's Playbook** (best GO + watchlist mood + one to watch), engine status, sidebar settings |
| **Dashboard** | Watchlist table with trust grade, regime, signal — your daily glance |
| **Deep Dive** | One stock: 20-year chart, key stats, hold-window heatmap, seasonality, hypothetical $1000 trade calculator, full backtest summary |
| **Backtest Lab** | Pick stock + model + horizon, see prediction vs actual line chart and metrics |
| **Forward Outlook** | Active GO signals only (often empty), with full trade plan including entry, exit, stop-loss, expected AUD return, **broker deep-link button**, **clipboard order ticket**, broker walkthrough |
| **Watchlist** | Current watchlist, in-watchlist recommender (which stocks have the strongest patterns), cache management |
| **Learn** | Beginner education on broker accounts, order types, T+2 settlement, AU CGT, dividends, common mistakes, full glossary |
| **Help** | The user guide rendered in-app for quick reference |
| **Journal** | Log real trades + self-grade your hit rate vs TRADEON's predictions |
| **Strategy Lab** | Toggle the three Tier-2 enhancements (GARCH / cross-asset / regime-stratified grade), run ON-vs-OFF backtest comparisons, apply globally |

The pipeline that powers the Dashboard, Forward Outlook, and Today's Playbook is centralised in `app_pipeline.py:analyse_one()`. All three pages share a single `@st.cache_data` so the heavy backtest work is paid once per session and reused everywhere.

Each enhancement toggle creates its own cache slot — `analyse_one()` is keyed on `(symbol, broker, enh_garch, enh_macro, enh_regime_grade, enh_recency_weighted, enh_drawdown_breaker)` — so flipping a toggle on the Strategy Lab triggers a one-time re-analysis with the new combination, then cached for an hour.

### Tier-2 enhancement modules (v1.2)

| Module | Toggle | Effect |
|--------|--------|--------|
| `core/volatility.py` | `use_garch` | GARCH(1,1) forecast → position-size multiplier in `[0.5, 1.5]` and CI band multiplier in `[0.7, 1.5]` |
| `core/macro.py` | `use_macro_confirm` | Index regime + VIX → mood (`favourable`/`neutral`/`hostile`); GO downgraded to WAIT when `hostile` |
| `core/regime_grade.py` | `use_regime_grade` | Replaces all-history trust grade with grade computed only on same-regime folds; falls back to vanilla when n < 5 |
| `core/settings.py` | — | Frozen `Enhancements` dataclass + session-state plumbing (no streamlit import in core) |

### Tier-3 enhancement modules (v1.3)

| Module | Toggle | Effect |
|--------|--------|--------|
| `core/forecast_weighted.py` | `use_recency_weighted` | Computes inverse-MAPE weights from the last `lookback_folds=5` walk-forward folds for each ensemble sub-model, then calls `ensemble_forecast(weights=...)`. Models without backtest data (Prophet) keep their 1/N share. Per-model weights capped at 70% / floored at 5%. Zero extra compute — re-uses `backtest_all` output. |
| `core/circuit_breaker.py` | `use_drawdown_breaker` | Pure function on a price df: `check_drawdown(df, window_days=30, threshold_pct=15)` returns a `CircuitBreakerStatus`. When `triggered=True` and the live signal is GO, `app_pipeline.analyse_one` downgrades it to WAIT with the breaker's interpretation prepended to the reasons list. Never creates new GOs. |

Both layer on top of the existing pipeline cleanly: recency-weighting changes the **forecast input** to `decide()`, the drawdown breaker is a **post-decision filter** like macro confirmation. Each gets its own cache slot in `analyse_one` (the `enh_recency_weighted` and `enh_drawdown_breaker` bools join the existing cache key).

### Backtest fold coverage (v1.2 fix)

`core/backtest._walk_forward_folds()` now defaults to `max_folds=60` and `prefer_recent=True`. Previously it was capped at 20 folds and kept the *oldest* folds, which meant a 20-year-old MSFT history showed predictions ending in ~2015. The pipeline used by the watchlist still passes `max_folds=20` to keep per-ticker run time manageable, but with `prefer_recent=True` those 20 folds are now the most recent ~5 years instead of the oldest 5. The Backtest Lab exposes the cap in its UI ("Last 5 years / Last 10 years / All available").

### Bundled price cache + nightly refresh action (v1.3)

To eliminate Streamlit Cloud's painful cold-start time (10-25 minutes refetching 25 symbols of 20-year OHLCV from yfinance), the parquet cache is now committed into the repo:

| Component | Path | Purpose |
|-----------|------|---------|
| Refresh script | `scripts/refresh_cache.py` | Re-fetches all watchlist symbols + FX + macro indices, writes to `data_cache/`, drops a `MANIFEST.json` |
| GitHub Action | `.github/workflows/refresh-cache.yml` | Runs the refresh script weekday mornings (06:30 AEST), commits + pushes the updated parquets |
| `.gitignore` carve-outs | `.gitignore` | Allows `data_cache/*.parquet` and `data_cache/MANIFEST.json` while still ignoring scratch files |
| TTL bump | `core/data.py:CACHE_TTL_HOURS` | Default raised from 12h to 36h (override with `$TRADEON_CACHE_TTL_HOURS`) so a missed nightly run doesn't immediately re-trigger live refetches |

The cache totals ~5 MB. Streamlit Cloud clones it on every deploy, so the Dashboard skips the slow `yfinance.history()` step entirely on a normal cold start. If the bundled cache is missing or stale beyond TTL the app silently falls back to live yfinance fetches — same code path as before, just slower.

---

## 12. Honest limitations

- **No exogenous shocks.** Statistical models cannot predict COVID, GFC, earnings surprises, regulatory change, geopolitical events. The trust grade will visibly drop after such events — this is the system working correctly.
- **Past performance does not guarantee future results.** Patterns from 2005-2025 may stop working in 2026.
- **Short-hold tax penalty.** Holdings under 12 months do not qualify for the 50% CGT discount. The app shows both pre-tax and post-tax outcomes so you can see if a 90-day trade still beats just holding for a year.
- **Free-tier latency.** On Streamlit Community Cloud's free tier, a normal cold-load Dashboard takes 30-90 seconds (bundled cache hit). When the bundled cache is missing or stale beyond TTL, it falls back to live yfinance fetches and can take 10-25 minutes. Subsequent loads within the hour are cached in memory and instant.
- **No real-time data.** yfinance gives end-of-day data with a 15-minute delay during market hours. TRADEON is built for swing trading, not day trading.
- **Decision support, not financial advice.** TRADEON is a tool for your own analysis. You bear all responsibility for trades you choose to place.
