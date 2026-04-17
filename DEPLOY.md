# Deploying TRADEON to Streamlit Community Cloud

This guide walks you through getting TRADEON running on the public internet
(behind a password) so you can use it from your tablet, phone, or any browser
without needing your laptop to be on.

**Time required:** about 30 minutes
**Cost:** $0 (Streamlit Community Cloud's free tier is plenty for personal use)

---

## What you'll end up with

- A URL like `https://tradeon-yourname.streamlit.app` you can open from any device.
- Auto-redeploy: every time you `git push`, the live app updates within a minute.
- Optional password protection so only you can access it.
- Prophet forecasting auto-enabled (Streamlit Cloud uses Python 3.11, where Prophet has wheels).

---

## Step 1 - create a GitHub repository

1. Go to <https://github.com/new>
2. Repository name: `tradeon` (or whatever you like)
3. **Set it to Private** (recommended - this is your personal trading tool)
4. **Do NOT** check "Add a README" or any of the initialise options - we already have those locally.
5. Click **Create repository**.
6. On the next page, GitHub shows you the repo's URL. Copy the HTTPS one - it looks like `https://github.com/YOUR_USERNAME/tradeon.git`.

## Step 2 - push your local code to GitHub

Open PowerShell in `C:\Users\Scotty\TRADEON` and run, replacing the URL with yours:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/tradeon.git
git branch -M main
git push -u origin main
```

If GitHub asks you to log in, use your GitHub username and a **personal access token** as the password (not your account password). You can create a token at <https://github.com/settings/tokens> (scope: `repo`).

After this, refresh the GitHub repo page in your browser and you should see all the project files.

## Step 3 - sign in to Streamlit Community Cloud

1. Go to <https://share.streamlit.io>
2. Click **Sign in with GitHub**
3. Authorise Streamlit to read your repositories (it needs this to deploy).

## Step 4 - deploy the app

1. Click **Create app** (or **New app**)
2. **Repository:** pick `YOUR_USERNAME/tradeon`
3. **Branch:** `main`
4. **Main file path:** `app.py`
5. **App URL:** customise the subdomain if you want (e.g. `tradeon-scotty`)
6. **Advanced settings:**
   - **Python version:** `3.11` (matches `runtime.txt`)
   - You can skip the Secrets section for now.
7. Click **Deploy**.

Streamlit Cloud will now:

- Clone your repo
- Install Python 3.11
- Run `pip install -r requirements.txt` (this takes 3-5 minutes the first time because Prophet has a large compile step)
- Launch your app

You'll see a build log scrolling past. When it finishes you'll be dropped on the live app.

## Step 5 - lock it down with a password (optional but recommended)

By default the app URL is publicly reachable by anyone who knows it. To require a login:

1. In the Streamlit Cloud dashboard, click your app, then **Settings -> Sharing**
2. Choose **Only specific people can view this app**
3. Add your own email address (the one tied to your GitHub account)
4. Save.

Now Streamlit requires a Google login matching that email before letting anyone in. Open the URL on your tablet, log in once, and it'll remember you.

## Step 6 - use it from your tablet

1. Open the app URL on your tablet's browser (Safari, Chrome, whatever).
2. **iPad:** tap the share button -> "Add to Home Screen". You now have a TRADEON icon that launches like an app.
3. **Android:** tap the menu -> "Add to Home screen". Same result.

---

## What happens when you change code

Workflow from now on:

```powershell
# edit code locally, test it
streamlit run app.py

# happy with it? commit and push
git add .
git commit -m "describe the change"
git push
```

About 30-60 seconds after the push, Streamlit Cloud rebuilds and reloads the live app. Refresh your tablet's browser to see the new version.

---

## What you should know about the free tier

| Aspect | Reality |
|---|---|
| **RAM** | 1 GB per app. TRADEON uses well under this. |
| **CPU** | Shared. First load after a sleep is slow (10-30 sec) because the watchlist analysis is heavy. |
| **Sleep** | After ~7 days of zero traffic, the app sleeps. Visiting wakes it (~30 sec cold start). |
| **Storage** | Ephemeral - the `data_cache/` parquet files vanish on every redeploy or wake. yfinance refetches on demand. This is fine. |
| **Bandwidth** | Plenty for personal use. |
| **Public** | The URL is public unless you enable the Google-login gate (Step 5). |

If you ever outgrow the free tier (you won't, for this app), the upgrade path is straightforward.

---

## Troubleshooting

### "Build failed - prophet won't install"

Make sure `runtime.txt` exists at the repo root and contains `python-3.11`. Double-check it was committed:

```powershell
git ls-files runtime.txt
```

If empty, run `git add runtime.txt; git commit -m "pin python"; git push`.

### "ModuleNotFoundError" on first load

Something missed `requirements.txt`. Add the missing package locally, push, redeploy.

### App is slow on first load

Expected - the Dashboard page runs walk-forward backtests on the entire watchlist. After the first load the results are cached in memory for an hour, so subsequent visits are fast. If you want to speed up cold starts, you can shrink the watchlist in `core/tickers.py`.

### "TooManyRequestsError" from yfinance

Yahoo throttles aggressive callers. The 1-hour cache in the Dashboard plus the on-disk parquet cache should keep you well under the limit. If it happens, click **Settings -> Reboot app** in Streamlit Cloud and wait 5 minutes.

---

## Reverting to local-only

If you ever want to delete the cloud deployment:

1. Streamlit Cloud dashboard -> your app -> **Settings -> Delete app**
2. (Optional) Delete the GitHub repo at `Settings -> Danger zone -> Delete this repository`

Your local copy is unaffected.
