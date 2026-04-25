# Speculation tab guide

This guide shows how to use the **Speculation** page as a manual, hypothesis-tracking lab.

## 1) What this page is for

It does **not** trade for you.

- It builds candidate LONG and SHORT ideas from TRADEON's forecast + trust pipeline.
- It lets you manually log a paper prediction using your chosen capital.
- It lets you manually close that prediction and measure what actually happened.
- It tracks results so you can evaluate signal quality before using real money.

## 2) How to get fresh candidates

When you open the tab, the candidate list is usually empty until you refresh it.

- Use **Refresh candidate list (quick)** for a fast shortlist.
- Use **Run full watchlist scan (21 stocks)** for a complete run.
- Use **Use optional media headlines** if you want sentiment context from free headlines.

The freshness banner below the refresh section shows when the list was last built and
warns you if it has become stale relative to your chosen "stale after" threshold.

## 3) Logging a prediction

1. Use the candidate selector to pick a seed candidate, or choose **(manual)**.
2. Set:
    - Direction (LONG/SHORT)
    - Entry price
    - Hold horizon
    - Predicted return %
    - Capital
3. Click **Add prediction**.

The register starts in **open** state.

## 4) Closing a prediction

1. Find your symbol in **Close an open prediction**.
2. Enter close date and close price.
3. Add optional note and click **Close selected prediction**.

TRADEON then records:

- realised return %
- fees + tax handling
- whether the directional thesis was correct
- prediction error versus the target %

## 5) Reading the register summary

Use the summary metrics and closed table to review:

- hit rate
- realised net return
- average holding days
- prediction error trend

If the hit rate and net returns are inconsistent, the market regime for your ideas may
not match what forecast scores alone suggest.

## 6) Best practices

- Keep this as a paper-only discipline until you trust your own judgment.
- Prefer fixed-size testing cycles (for example, 45–60 days) for cleaner outcome comparisons.
- Don’t mix manual and auto-closure logic; the register is intentionally simple and explicit.

## 7) Troubleshooting

### Speculation list is empty

That is normal first thing after opening the page.

- Use **Refresh candidate list (quick)** or **Run full watchlist scan (21 stocks)**.
- The list is not auto-updating; you control when it is regenerated.

### `streamlit : The term 'streamlit' is not recognized`

You need to run the app in an activated Python environment.

```powershell
cd C:\Users\Scotty\TRADEON
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

If `streamlit` is still unavailable, use:

```powershell
python -m streamlit run app.py
```

Other quick checks:

- `app.py` is not directly executable as a PowerShell command; use `python app.py` for scripts.
- If you run outside the repo folder, change into `C:\Users\Scotty\TRADEON` first.

## 8) Record-keeping note

If you decide not to use Speculation, that is fully supported. It does not affect other pages (Dashboard, Forward Outlook, Journal, Strategy Lab). Use it only when you want a manual hypothesis lab.

