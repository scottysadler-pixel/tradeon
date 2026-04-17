"""Plain-English definitions for every metric and term used in the app.

Wired into Streamlit `help=` tooltips. Goal: nothing in the UI is a mystery
to a beginner.
"""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    # Returns / risk
    "CAGR": (
        "Compound Annual Growth Rate. The average yearly return you would have "
        "earned if growth had been smooth. A CAGR of 10% means your money would "
        "have doubled roughly every 7 years."
    ),
    "Volatility": (
        "How wildly the price swings. Measured as the standard deviation of "
        "yearly returns. Higher volatility = bigger ups AND bigger downs."
    ),
    "Max Drawdown": (
        "The biggest peak-to-trough fall in the stock's history during the "
        "lookback period. -50% means it once fell by half before recovering."
    ),
    "Sharpe Ratio": (
        "Reward per unit of risk. Above 1.0 is decent, above 2.0 is excellent. "
        "Compares return to how bumpy the ride was getting there."
    ),
    "Pattern Strength": (
        "How forecastable this stock is at all. Some stocks have repeating "
        "patterns; others are pure noise. Higher = more predictable. Below "
        "0.3 means we don't trust ANY model on this name."
    ),
    # Forecast / model accuracy
    "MAPE": (
        "Mean Absolute Percentage Error. On average, how far off our "
        "predictions were as a %. MAPE of 5% means our forecasts missed the "
        "actual price by 5% on average."
    ),
    "RMSE": (
        "Root Mean Squared Error. Like MAPE but in dollars and penalises big "
        "misses more than small ones."
    ),
    "Directional Accuracy": (
        "How often we got the up/down call right. 50% is a coin flip. Anything "
        "below 55% is no better than guessing. Above 60% is meaningful."
    ),
    "CI Coverage": (
        "Confidence Interval coverage. Our 80% confidence band should contain "
        "the actual price about 80% of the time. If it's catching only 50%, "
        "the model is overconfident."
    ),
    "Trust Grade": (
        "A-F letter grade based on how well the app's past predictions matched "
        "reality on this specific stock - measured AFTER fees and tax. A = "
        "highly reliable, F = worse than flipping a coin. The grade updates "
        "with every refresh, so it stays honest as conditions change."
    ),
    "Naive Baseline": (
        "The dumbest possible forecast: 'tomorrow's price = today's price'. "
        "Many fancy AI models secretly do WORSE than this. We always show our "
        "results next to this baseline to keep ourselves honest."
    ),
    # Regime / signals
    "Regime": (
        "The current 'mood' of the market: bull (rising), bear (falling), or "
        "sideways (going nowhere). Forecasts only use historical periods that "
        "match the current regime."
    ),
    "Hold Window": (
        "The historically best time of year to buy this stock and the date to "
        "sell it. E.g. 'buy late October, sell late February' if that combo "
        "produced consistent gains over the past 20 years."
    ),
    "Hit Rate": (
        "What % of historical years that hold-window actually delivered a "
        "profit. 73% means it worked in 73 out of every 100 historical years."
    ),
    "Stop-Loss": (
        "A price you decide in advance to sell at if the stock falls, to cap "
        "your losses. Set too tight and normal wiggles trigger it; set too "
        "loose and it doesn't protect you. We suggest one based on each "
        "stock's typical drawdown."
    ),
    "Position Size": (
        "How much of your money to put into a single trade. We suggest more "
        "for low-volatility stocks and less for high-volatility ones, so each "
        "trade carries similar risk."
    ),
    # Technicals
    "RSI": (
        "Relative Strength Index. A momentum gauge from 0 to 100. Above 70 = "
        "the stock has run up hard recently and may be due for a pullback. "
        "Below 30 = beaten down, may be due for a bounce."
    ),
    "MACD": (
        "Moving Average Convergence Divergence. When the fast line crosses "
        "above the slow line, momentum is turning bullish; below = bearish. "
        "Useful as confirmation, not as a sole signal."
    ),
    "Bollinger Bands": (
        "Two lines drawn 2 standard deviations above and below the 20-day "
        "average price. Price touching the upper band = unusually high vs "
        "recent trend; lower band = unusually low."
    ),
    # Trading mechanics
    "Market Order": (
        "Buy/sell immediately at whatever the current best price is. Fast but "
        "you don't control the exact price - in fast markets you can pay a bit "
        "more (or get a bit less) than you expected."
    ),
    "Limit Order": (
        "Buy only if the price drops to (or sells only if it rises to) a price "
        "YOU choose. You control the price but the trade may never happen if "
        "the market doesn't reach your level."
    ),
    "T+2 Settlement": (
        "After you sell, the cash isn't actually in your account for 2 "
        "business days (T+2 = trade date plus 2). Plan for this if you need "
        "the money quickly."
    ),
    "CGT Discount": (
        "In Australia, if you hold a share for at least 12 months before "
        "selling, you only pay tax on HALF the capital gain. Selling earlier "
        "means paying tax on the full gain at your marginal rate."
    ),
    "Brokerage Fee": (
        "What your broker charges per trade. Ranges from ~A$3 (Stake, Pearler) "
        "to A$10-30 (CommSec) per trade. Eats directly into profit, especially "
        "on small trades."
    ),
    "Franking Credits": (
        "When an Australian company pays a dividend from already-taxed "
        "profits, you get a 'franking credit' that offsets tax you'd otherwise "
        "owe. Mostly applies to AU shares; doesn't change the price chart."
    ),
    # Honesty
    "Walk-Forward Backtest": (
        "Pretending we're back in time, making a forecast, then checking what "
        "REALLY happened. Repeated rolling through history. The most honest "
        "way to test if a strategy actually works."
    ),
    "Ensemble": (
        "Running multiple forecasting models in parallel and averaging their "
        "predictions, weighted by which has been most accurate recently. "
        "Usually beats any single model."
    ),
}


def explain(term: str) -> str:
    """Return the plain-English definition of a term, or empty string."""
    return GLOSSARY.get(term, "")
