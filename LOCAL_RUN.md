# Run TRADEON locally (full speed, optional)

The Streamlit Cloud deployment is fine for casual use, but a local run is
noticeably snappier:

- No cold-start container delay.
- All 21 stocks compute in parallel using your machine's CPU (an M2 iPad's
  worth of cores per worker, instead of the single shared core Cloud gives you).
- The disk cache lives on your SSD permanently — it never gets wiped.
- You can hit the app from your iPad over Wi-Fi using your laptop as the server.

Total setup time: about 5 minutes the first time, then `streamlit run app.py`
forever after.

---

## Prerequisites (one-time, per machine)

You need these installed:

- **Python 3.11 or newer** ([download](https://www.python.org/downloads/) — pick
  "Add Python to PATH" on Windows).
- **Git** ([download](https://git-scm.com/downloads)).

Verify both are on your PATH:

```bash
python --version    # should print 3.11+ (or 3.12, 3.13, 3.14)
git --version
```

---

## Step 1 — Clone the repo

Pick a folder you'll remember. Examples:

- macOS / Linux: `~/code/TRADEON`
- Windows: `C:\Users\<you>\TRADEON`

```bash
git clone https://github.com/<your-github-username>/TRADEON.git
cd TRADEON
```

(If you forked it or cloned it before, just `cd` into the folder and run
`git pull` to fetch the latest.)

---

## Step 2 — Create a virtual environment

This keeps TRADEON's dependencies isolated from any other Python projects.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You'll know it worked when the prompt shows `(.venv)` at the start.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This pulls in Streamlit, pandas, yfinance, statsmodels, scikit-learn, and the
forecasting libraries. Takes about 60 seconds on a typical broadband
connection.

---

## Step 4 — Run the app

```bash
streamlit run app.py
```

Streamlit prints two URLs:

- `Local URL: http://localhost:8501` — open this in your laptop browser.
- `Network URL: http://192.168.x.x:8501` — keep this one handy for the iPad
  (next section).

Press **Ctrl+C** in the terminal to stop the server. Re-run anytime with the
same `streamlit run app.py`.

---

## Step 5 (optional) — Open it on your iPad over Wi-Fi

Both devices must be on the same Wi-Fi network (e.g. your home router).

1. Make sure the laptop is awake and the `streamlit run app.py` terminal is
   still open.
2. On the iPad, open Safari and type the **Network URL** Streamlit printed
   (the one starting with `192.168.` or `10.0.`). For example:
   `http://192.168.1.42:8501`.
3. The first time, your OS firewall may ask whether to allow incoming
   connections to Python — click **Allow** (or "Allow on private networks").

### Add to Home Screen

While the app is open in Safari on the iPad:

1. Tap the **Share** icon (square with up-arrow).
2. Scroll down, tap **Add to Home Screen**.
3. The icon will be labelled "TRADEON" with the chart emoji and open like
   a native app (full-screen, no Safari address bar). Status bar will be dark
   to match the app theme.

This works against both the local URL and the Streamlit Cloud URL — pick
whichever you prefer.

---

## Speed expectations

| Action | Streamlit Cloud (free) | Local (M2 / Ryzen / similar) |
|---|---|---|
| Cold start (first ever load) | 30-90 s | 2-5 s |
| First playbook scan (21 stocks) | 90-180 s | 20-40 s |
| Subsequent playbook scan (warm cache) | < 1 s | < 1 s |
| Backtest Lab — first model run | 8-15 s | 2-4 s |
| Backtest Lab — repeat (cached) | < 0.5 s | < 0.2 s |

The numbers above assume `requirements.txt` installed cleanly (no
fall-back to slow-path Python implementations of NumPy / scikit-learn).

---

## Troubleshooting

**`streamlit: command not found`**
You forgot to activate the venv. Re-run the activate step in Section 2.

**iPad "Safari can't open the page" or "address is invalid"**
The laptop went to sleep, or you're on different Wi-Fi networks (e.g. iPad
on guest network, laptop on main). Double-check both, and disable any VPN
on the iPad.

**Firewall blocks connection (Windows)**
Open "Windows Defender Firewall with Advanced Security" → Inbound Rules → New
Rule → Port → TCP 8501 → Allow. Or just answer "Yes" to the popup the first
time you run Streamlit.

**Stocks fail to load with "rate-limited" or empty data**
yfinance occasionally throttles. The app's stale-cache fallback will paper
over short outages. If it persists for hours, run the manual refresh:

```bash
python scripts/refresh_cache.py
```

---

## Updating to the latest code

```bash
git pull
pip install -r requirements.txt    # only needed if requirements.txt changed
streamlit run app.py
```

That's it. No deploy step needed — local always reflects whatever is on
your `main` branch.
