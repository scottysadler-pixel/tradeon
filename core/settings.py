"""Strategy enhancement settings.

Each "enhancement" is an opt-in tweak to the default forecasting / signalling
pipeline. Users toggle them in the Strategy Lab page; this module is the
single source of truth for which ones are active.

Design principles:
  * All toggles default to OFF - the default app behaviour is the v1 baseline,
    so users can always compare against it.
  * Settings are plain dataclass values - the Streamlit layer mirrors them
    into st.session_state, but `core/` never imports streamlit, so this
    module stays unit-testable.
  * Each enhancement is independent. Turning one on never silently turns
    another on.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Enhancements:
    """Toggle bundle. All False = vanilla v1 behaviour."""

    # 1. GARCH-aware position sizing + breathing CI bands.
    #    When ON: position size shrinks when GARCH expects above-trend vol,
    #    grows when GARCH expects calm conditions; CI bands widen/narrow.
    use_garch: bool = False

    # 2. Cross-asset confirmation.
    #    When ON: GO signal additionally requires the parent index (^GSPC for
    #    US, ^AXJO for ASX) to NOT be in a bear regime, AND VIX to be below 25.
    use_macro_confirm: bool = False

    # 3. Regime-stratified trust grade.
    #    When ON: trust grade is computed using only folds whose start-regime
    #    matches the CURRENT detected regime - so a bull-market grade is judged
    #    against the model's bull-market track record, not its all-history one.
    use_regime_grade: bool = False

    # Internal: tag set by ApplyForBacktest to remember which combo produced
    # which result, so the Strategy Lab can display ON/OFF comparisons.
    label: str = "default"

    def any_active(self) -> bool:
        return self.use_garch or self.use_macro_confirm or self.use_regime_grade

    def short_label(self) -> str:
        if not self.any_active():
            return "vanilla"
        on = []
        if self.use_garch:
            on.append("garch")
        if self.use_macro_confirm:
            on.append("macro")
        if self.use_regime_grade:
            on.append("regime-grade")
        return "+".join(on)


def all_off() -> Enhancements:
    return Enhancements()


def all_on() -> Enhancements:
    return Enhancements(
        use_garch=True,
        use_macro_confirm=True,
        use_regime_grade=True,
        label="all-on",
    )


def with_only(name: str) -> Enhancements:
    """Build an Enhancements bundle with exactly one toggle on."""
    base = Enhancements(label=name)
    if name == "garch":
        return replace(base, use_garch=True)
    if name == "macro":
        return replace(base, use_macro_confirm=True)
    if name == "regime-grade":
        return replace(base, use_regime_grade=True)
    return base


# ----- Streamlit session_state helpers (UI layer wraps these) ----------

SESSION_KEY = "_tradeon_enhancements"


def from_session(session_state) -> Enhancements:
    """Fetch the active Enhancements from streamlit's session_state.

    `session_state` is duck-typed so this stays import-free of streamlit.
    """
    val = session_state.get(SESSION_KEY) if hasattr(session_state, "get") else None
    if isinstance(val, Enhancements):
        return val
    return all_off()


def to_session(session_state, enhancements: Enhancements) -> None:
    session_state[SESSION_KEY] = enhancements
