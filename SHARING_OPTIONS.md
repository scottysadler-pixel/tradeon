# Sharing TRADEON with Others - Options Guide

**Context:** TRADEON currently has single-user data storage. This guide outlines secure options for sharing or demoing the app to others (e.g., family, friends) without exposing your personal Trade Journal data.

**Status:** NOT YET IMPLEMENTED - saved for future implementation when ready.

---

## The Problem

Current state:
- App uses Streamlit Cloud access control (Google login required)
- One shared data store: `data_cache/journal.csv`
- If you add someone's email to access list, they'd see YOUR Trade Journal entries
- A simple "demo mode toggle" isn't secure (they could just turn it off)

---

## Secure Solutions

### Option A: Separate Demo App (5 minutes - Recommended for quick demos)

**What it is:** Create a second Streamlit Cloud app deployment pointing to the same repo.

**Setup:**
1. Streamlit Cloud dashboard → "New app"
2. Repository: `YOUR_USERNAME/tradeon`
3. Branch: `main`
4. App URL: `tradeon-demo.streamlit.app` (different from your main one)
5. Sharing: Set to "Public" or "Anyone with the link"
6. Click Deploy

**Result:**
- You have TWO apps:
  - `tradeon-scotty.streamlit.app` → your private app (your email only, your real trades)
  - `tradeon-demo.streamlit.app` → demo app (public or specific emails, clean journal)
- Completely separate data stores
- No way for demo users to access your real journal

**How to use:**
- Log some practice trades in the demo app to show how it works
- Give demo URL to anyone you want to show
- Keep your real app URL private

**Pros:**
- ✅ Perfect data isolation
- ✅ 5 minutes to set up
- ✅ Zero code changes needed
- ✅ Free (Streamlit allows multiple apps)
- ✅ Can pre-populate demo with example trades

**Cons:**
- ⚠️ Two separate apps to maintain (both update when you push to `main`)
- ⚠️ Demo has its own cache/data that doesn't sync with your real app

**Cost:** $0 (both apps run on free tier)

---

### Option B: Per-User Data Isolation (30 minutes - Best for ongoing sharing)

**What it is:** Add user authentication to the app code so each logged-in user gets their own journal.

**How it works:**
- Uses Streamlit's built-in `st.experimental_user` (available when deployed with Google auth)
- Journal saves to `data_cache/journal_{user_email_hash}.csv`
- Each user only sees their own trades
- Dashboard/signals/backtests shared (same watchlist for everyone)

**Code changes required:**
```python
# In pages/8_Journal.py
user = st.experimental_user
user_email = user.email if user.email else "default"
user_hash = hashlib.md5(user_email.encode()).hexdigest()[:8]
JOURNAL_PATH = CACHE_DIR / f"journal_{user_hash}.csv"
```

**Setup:**
1. Implement user-aware journal paths (code changes)
2. Add your dad's email to Streamlit Cloud access list
3. Each person logs in with their own Google account
4. Each gets their own isolated journal

**Pros:**
- ✅ Single app, multiple users
- ✅ Secure - based on authentication, not toggles
- ✅ Each user has private journal
- ✅ Easy to add more users later (just add emails)

**Cons:**
- ⚠️ Requires code changes (30 min implementation)
- ⚠️ Only works when deployed with auth (won't work locally without login)
- ⚠️ All users share same signals/cache (not a problem for most use cases)

**Implementation time:** ~30 minutes

---

### Option C: Demo Branch Deployment (10 minutes - Medium security)

**What it is:** Create a `demo` git branch with Journal page removed from the code, deploy a second app pointing to that branch.

**Setup:**
1. Create new branch: `git checkout -b demo`
2. Remove Journal page: `git rm pages/8_Journal.py`
3. Commit: `git commit -m "Remove journal for demo branch"`
4. Push: `git push -u origin demo`
5. Streamlit Cloud → "New app" → point to `demo` branch
6. Share demo app URL

**Result:**
- Main app (`main` branch) = full features, your email only
- Demo app (`demo` branch) = no Journal page at all
- He literally can't access Journal - it doesn't exist in demo

**Pros:**
- ✅ Secure - Journal doesn't exist in demo branch
- ✅ No risk of your data being seen
- ✅ Easy to maintain (merge main → demo periodically)

**Cons:**
- ⚠️ He can't try the Journal feature at all
- ⚠️ Two branches to keep in sync
- ⚠️ Any feature updates need to be merged to demo branch manually

---

### Option D: Password-Protected Demo Mode (15 minutes - Moderate security)

**What it is:** Add a demo mode that's activated by a password in the sidebar.

**How it works:**
```python
# In sidebar
demo_password = st.text_input("Demo password", type="password")
if demo_password == "secret123":
    st.session_state["demo_mode"] = True

# In Journal page
if st.session_state.get("demo_mode"):
    st.info("Journal disabled in demo mode")
else:
    # show normal journal
```

**Pros:**
- ✅ Single app
- ✅ Quick to implement
- ✅ Can enable/disable easily

**Cons:**
- ⚠️ Security through obscurity (password could be shared/guessed)
- ⚠️ If he learns the password to disable demo mode, he could access journal
- ⚠️ Less secure than authentication-based approaches

---

## Comparison Table

| Option | Setup Time | Security | Maintenance | Best For |
|--------|-----------|----------|-------------|----------|
| **A. Per-User Isolation** | 30 min | 🟢 High | Easy | Ongoing sharing, multiple users |
| **B. Separate Demo App** | 5 min | 🟢 Perfect | Easy | Quick demos, showing features |
| **C. Demo Branch** | 10 min | 🟢 High | Medium | Demos without Journal access |
| **D. Password Demo** | 15 min | 🟡 Moderate | Easy | Casual demos, trusted users |

---

## Recommended Path

**For showing your dad once or twice:**
→ **Option B (Separate Demo App)** - 5 minutes, zero security concerns

**If he wants to use it regularly:**
→ **Option A (Per-User Isolation)** - proper multi-user setup

---

## What to Do Later

When you're ready to set this up:

**For Option B (quick demo):**
1. Tell me "let's do the demo app" 
2. I'll walk you through the Streamlit Cloud steps
3. Takes 5 minutes total

**For Option A (per-user isolation):**
1. Tell me "let's implement multi-user"
2. I'll add the authentication code
3. Takes 30 minutes total
4. Test it before sharing

---

## Current Access Control Reminder

**Your app URL:** `https://tradeon-7.streamlit.app` (or similar)

**Current access:** Only your email (set in Streamlit Cloud → Settings → Sharing)

**How you log in:** 
- Visit the URL
- Streamlit redirects to Google login
- Uses your Google account (the "passkey" is actually Google OAuth)
- Once logged in, Streamlit remembers you on that device

**To view/change access:**
1. Go to <https://share.streamlit.io>
2. Find your app
3. Settings → Sharing
4. See who has access

---

**Saved for later implementation. Come back to this doc when ready to share!**
