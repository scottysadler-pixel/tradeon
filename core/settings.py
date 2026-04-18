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

from dataclasses import dataclass, replace


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

    # 4. Recency-weighted ensemble.
    #    When ON: the prophet/holt-winters/arima ensemble re-weights its
    #    sub-models by their MAPE over the last 5 walk-forward folds, instead
    #    of equal weighting. The model that has been most accurate recently
    #    gets the largest say in the next forecast.
    use_recency_weighted: bool = False

    # 5. Drawdown circuit-breaker.
    #    When ON: a stock that has fallen more than 15% from its peak in the
    #    last 30 trading days has any GO signal forced down to WAIT. Catches
    #    "falling knife" situations that statistical models systematically
    #    misjudge.
    use_drawdown_breaker: bool = False

    # Internal: tag set by ApplyForBacktest to remember which combo produced
    # which result, so the Strategy Lab can display ON/OFF comparisons.
    label: str = "default"

    def any_active(self) -> bool:
        return (
            self.use_garch
            or self.use_macro_confirm
            or self.use_regime_grade
            or self.use_recency_weighted
            or self.use_drawdown_breaker
        )

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
        if self.use_recency_weighted:
            on.append("recency")
        if self.use_drawdown_breaker:
            on.append("breaker")
        return "+".join(on)


def all_off() -> Enhancements:
    return Enhancements()


def all_on() -> Enhancements:
    return Enhancements(
        use_garch=True,
        use_macro_confirm=True,
        use_regime_grade=True,
        use_recency_weighted=True,
        use_drawdown_breaker=True,
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
    if name == "recency":
        return replace(base, use_recency_weighted=True)
    if name == "breaker":
        return replace(base, use_drawdown_breaker=True)
    return base


# ----- Streamlit session_state helpers (UI layer wraps these) ----------

SESSION_KEY = "tradeon_enhancements"

# Bumped whenever new fields are added to Enhancements. Stale objects with a
# missing or older _schema_version are silently rebuilt with the new shape so
# we never hand back an instance that callers expect to have new fields on.
_SCHEMA_VERSION = 2


def from_session(session_state) -> Enhancements:
    """Fetch the active Enhancements from streamlit's session_state.

    Defensive against schema drift: if a stale `Enhancements` instance is
    present (e.g. pickled by an older deploy that didn't have the v1.3 fields)
    we rebuild it field-by-field via `getattr` with current defaults rather
    than handing it back as-is. Otherwise downstream code crashes with
    AttributeError on the missing fields.

    `session_state` is duck-typed so this stays import-free of streamlit.
    """
    val = session_state.get(SESSION_KEY) if hasattr(session_state, "get") else None
    if val is None:
        return all_off()
    if isinstance(val, Enhancements):
        # Fast path - already the current class with all current fields.
        # We still rebuild defensively because `isinstance` returns True even
        # when the class definition has been re-imported with new fields and
        # the stored object was constructed under the older definition.
        return _migrate(val)
    # Anything else (dict, None, mangled state) -> safe defaults.
    return all_off()


def _migrate(val: Enhancements) -> Enhancements:
    """Rebuild an Enhancements from whatever attributes the stored object has.

    Missing fields get the current default. Returns a fresh instance built
    from the live class definition, so callers can safely access any field.
    """
    return Enhancements(
        use_garch=bool(getattr(val, "use_garch", False)),
        use_macro_confirm=bool(getattr(val, "use_macro_confirm", False)),
        use_regime_grade=bool(getattr(val, "use_regime_grade", False)),
        use_recency_weighted=bool(getattr(val, "use_recency_weighted", False)),
        use_drawdown_breaker=bool(getattr(val, "use_drawdown_breaker", False)),
        label=str(getattr(val, "label", "default") or "default"),
    )


def to_session(session_state, enhancements: Enhancements) -> None:
    session_state[SESSION_KEY] = enhancements


def clear_session(session_state) -> None:
    """Remove any stored Enhancements from session_state.

    Used by the Strategy Lab "Clear cached settings" recovery button so the
    user can flush a stale state without restarting the deploy.
    """
    if hasattr(session_state, "__delitem__") and SESSION_KEY in session_state:
        try:
            del session_state[SESSION_KEY]
        except Exception:
            session_state[SESSION_KEY] = all_off()
