"""Help page - renders USER_GUIDE.md inside the app.

One source of truth: edit USER_GUIDE.md and this page reflects it.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui_helpers import page_setup, render_disclaimer

page_setup("Help")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUIDE_PATH = PROJECT_ROOT / "USER_GUIDE.md"
QUICK_START_PATH = PROJECT_ROOT / "QUICK_START.md"
BACKTEST_WALKTHROUGH_PATH = PROJECT_ROOT / "BACKTEST_LAB_WALKTHROUGH.md"
CALENDAR_GUIDE_PATH = PROJECT_ROOT / "CALENDAR_FEATURE_GUIDE.md"
SPECULATION_GUIDE_PATH = PROJECT_ROOT / "SPECULATION_GUIDE.md"

st.markdown("### 📚 Documentation Library")

# Quick access to all guides
guide_cols = st.columns(5)

with guide_cols[0]:
    if QUICK_START_PATH.exists():
        st.download_button(
            "🚀 Quick Start",
            data=QUICK_START_PATH.read_text(encoding="utf-8"),
            file_name="QUICK_START.md",
            mime="text/markdown",
            help="One-page guide: what each page does + daily workflow",
            width="stretch",
        )

with guide_cols[1]:
    if BACKTEST_WALKTHROUGH_PATH.exists():
        st.download_button(
            "🧪 Backtest Lab",
            data=BACKTEST_WALKTHROUGH_PATH.read_text(encoding="utf-8"),
            file_name="BACKTEST_LAB_WALKTHROUGH.md",
            mime="text/markdown",
            help="Practice testing without risk - step-by-step examples",
            width="stretch",
        )

with guide_cols[2]:
    if CALENDAR_GUIDE_PATH.exists():
        st.download_button(
            "📅 Calendar",
            data=CALENDAR_GUIDE_PATH.read_text(encoding="utf-8"),
            file_name="CALENDAR_FEATURE_GUIDE.md",
            mime="text/markdown",
            help="How to use trade exit reminders and upcoming exits panel",
            width="stretch",
        )

with guide_cols[3]:
    if SPECULATION_GUIDE_PATH.exists():
        st.download_button(
            "🔮 Speculation",
            data=SPECULATION_GUIDE_PATH.read_text(encoding="utf-8"),
            file_name="SPECULATION_GUIDE.md",
            mime="text/markdown",
            help="Paper-only LONG/SHORT idea tracking workflow",
            width="stretch",
        )

with guide_cols[4]:
    if GUIDE_PATH.exists():
        st.download_button(
            "📖 Full Manual",
            data=GUIDE_PATH.read_text(encoding="utf-8"),
            file_name="TRADEON_User_Guide.md",
            mime="text/markdown",
            help="Complete USER_GUIDE (673 lines) - save for offline reading",
            width="stretch",
        )

st.divider()

st.caption(
    "💡 The Full Manual is shown below. For quicker reference, download the Quick Start or "
    "specific topic guides above."
)

st.markdown("---")
st.markdown("### Complete User Guide")

st.caption(
    "To print: press Ctrl+P (Windows) or Cmd+P (Mac) "
    "and choose 'Save as PDF' or send to your printer."
)


if GUIDE_PATH.exists():
    st.markdown(GUIDE_PATH.read_text(encoding="utf-8"))
else:
    st.error(
        f"Could not find USER_GUIDE.md at {GUIDE_PATH}. "
        "If you cloned the repo, make sure USER_GUIDE.md is present at the project root."
    )

render_disclaimer()
