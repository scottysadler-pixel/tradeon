"""Help page - renders USER_GUIDE.md inside the app.

One source of truth: edit USER_GUIDE.md and this page reflects it.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui_helpers import page_setup, render_disclaimer

page_setup("Help")

GUIDE_PATH = Path(__file__).resolve().parent.parent / "USER_GUIDE.md"

st.caption(
    "Plain-English user manual. To print: press Ctrl+P (Windows) or Cmd+P (Mac) "
    "and choose 'Save as PDF' or send to your printer. The same content lives in "
    "USER_GUIDE.md in the project repo."
)

c1, c2 = st.columns([1, 3])
with c1:
    st.download_button(
        label="Download as Markdown",
        data=GUIDE_PATH.read_text(encoding="utf-8") if GUIDE_PATH.exists() else "",
        file_name="TRADEON_User_Guide.md",
        mime="text/markdown",
        disabled=not GUIDE_PATH.exists(),
        help="Save a copy to your tablet or laptop for offline reading.",
    )
with c2:
    st.markdown(
        "Tip: bookmark this page on your tablet for one-tap access. "
        "On iPad: share button -> 'Add to Home Screen'."
    )

st.divider()

if GUIDE_PATH.exists():
    st.markdown(GUIDE_PATH.read_text(encoding="utf-8"))
else:
    st.error(
        f"Could not find USER_GUIDE.md at {GUIDE_PATH}. "
        "If you cloned the repo, make sure USER_GUIDE.md is present at the project root."
    )

render_disclaimer()
