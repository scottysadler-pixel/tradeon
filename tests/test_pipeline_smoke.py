"""End-to-end pipeline smoke tests.

This is the "click on everything" test for the per-stock analysis pipeline.
It runs entirely without a browser or streamlit runtime by exercising:

  1. Every page module imports cleanly (catches the kind of stale-reference
     bug that bit us when we added the v1.3 toggles - a page would crash
     on import because it referenced an `Enhancements` field that didn't
     exist yet, before any UI could even render an error).

  2. `analyse_one` runs cleanly for a representative ASX + US ticker across
     every individual toggle AND with all toggles on, asserting the result
     dict has the expected shape, signal grades are valid, forecast bands
     are properly ordered, and toggle-specific fields appear / vanish as
     they should.

  3. `analyse_all` runs cleanly across the entire watchlist with vanilla
     toggles (the safety net - if this is green, the Dashboard / Forward
     Outlook / Today's Playbook all have valid data to render).

NOTE: We deliberately do NOT use `streamlit.testing.v1.AppTest` here. That
framework leaks `st.form()` global context between cases when run inside
the same pytest process, producing a stream of false-positive
"st.button can't be used in an st.form()" failures that don't reflect any
real bug in the app. Per-page rendering is verified manually + via the
real Streamlit Cloud deploy.

Reads price data from the local `data_cache/` parquet files, so the suite
never hits the network. If the cache is empty the suite is skipped (not
failed) so a fresh checkout that hasn't run the cache-refresh action yet
won't go red.
"""

from __future__ import annotations

import ast
import importlib
import py_compile
import sys
from pathlib import Path

import pytest

# Make sure the repo root is on sys.path even when pytest is invoked from elsewhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data import _cache_path  # noqa: E402
from core.settings import all_off  # noqa: E402

# ----- Sample tickers used by the per-stock smoke -----
# Two symbols only, to keep total runtime under ~5 minutes:
#   - MSFT: clean US history, exercises the USD->AUD FX path
#   - BHP.AX: ASX symbol, exercises the .AX adjusted-price path
SMOKE_SYMBOLS = ["MSFT", "BHP.AX"]


def _has_local_cache(symbol: str) -> bool:
    """True if the adjusted parquet cache exists for this symbol."""
    return _cache_path(symbol, adjusted=True).exists()


pytestmark = pytest.mark.skipif(
    not all(_has_local_cache(s) for s in SMOKE_SYMBOLS),
    reason=(
        f"Local parquet cache missing for one of {SMOKE_SYMBOLS}. "
        "Run `python scripts/refresh_cache.py` (or trigger the GitHub Action) "
        "to populate data_cache/ before running the smoke suite."
    ),
)


# =====================================================================
# Page-file static checks
# =====================================================================
# We deliberately do NOT do `importlib.import_module(page)` here, because
# many pages run heavy work (load_data + backtest_all) at module top-level,
# so importing them executes the pipeline and takes ~60s each. That kind
# of runtime check is already covered by `test_analyse_one_smoke`.
#
# Instead we do two cheap static checks per page file:
#   1. `py_compile.compile()` - confirms the file parses + bytecode-compiles
#      cleanly. Catches syntax errors and indentation bugs.
#   2. AST scan of every `from X import Y` - confirms each module X exists
#      AND each name Y is actually exported by X. This is the check that
#      would have caught the stale `from core.settings import ...` bug if
#      we'd renamed a field.

PAGE_FILES = sorted(
    p for p in (ROOT / "pages").glob("*.py")
    if not p.name.startswith("_")
)


@pytest.mark.parametrize("page_path", PAGE_FILES, ids=lambda p: p.name)
def test_page_file_compiles(page_path: Path):
    """Page file must parse + bytecode-compile cleanly (no syntax errors)."""
    try:
        py_compile.compile(str(page_path), doraise=True)
    except py_compile.PyCompileError as e:
        pytest.fail(f"{page_path.name} failed to compile:\n{e}")


@pytest.mark.parametrize("page_path", PAGE_FILES, ids=lambda p: p.name)
def test_page_imports_resolve(page_path: Path):
    """Every `from X import Y` in a page must resolve to a real attribute.

    This is the check that would have caught the v1.3 stale-field bug
    early: if a page wrote `from core.settings import use_recency_weighted`
    and that name didn't exist on `core.settings`, this test would fail
    with a clear "page X imports name Y from module Z but Z has no such
    attribute" message - long before Streamlit Cloud users hit it.
    """
    source = page_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(page_path))

    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module is None or node.level != 0:
            continue  # relative imports - skip
        try:
            module = importlib.import_module(node.module)
        except Exception as e:  # noqa: BLE001
            failures.append(
                f"  line {node.lineno}: cannot import module `{node.module}`: {e!r}"
            )
            continue
        for alias in node.names:
            name = alias.name
            if name == "*":
                continue
            if not hasattr(module, name):
                failures.append(
                    f"  line {node.lineno}: `{node.module}` has no attribute `{name}` "
                    f"(referenced as `from {node.module} import {name}`)"
                )

    if failures:
        pytest.fail(
            f"{page_path.name} has {len(failures)} unresolved import(s):\n"
            + "\n".join(failures)
        )


# =====================================================================
# Per-stock pipeline smoke
# =====================================================================
# Each toggle gets its own one-hot test so a failure points at exactly
# which enhancement broke. Plus an "all off" baseline and an "all on"
# stress test.

TOGGLE_COMBOS = [
    ("vanilla",      dict()),
    ("garch_only",   dict(enh_garch=True)),
    ("macro_only",   dict(enh_macro=True)),
    ("regime_only",  dict(enh_regime_grade=True)),
    ("recency_only", dict(enh_recency_weighted=True)),
    ("breaker_only", dict(enh_drawdown_breaker=True)),
    (
        "all_on",
        dict(
            enh_garch=True, enh_macro=True, enh_regime_grade=True,
            enh_recency_weighted=True, enh_drawdown_breaker=True,
        ),
    ),
]

REQUIRED_RESULT_KEYS = {
    "symbol", "name", "ticker", "df", "spot_aud",
    "trust_grade", "trust_score", "regime",
    "signal", "signal_obj", "signal_headline",
    "expected_90d_pct", "forecast", "naive",
    "stops", "hold", "earnings", "technicals",
    "ensemble_directional_pct", "naive_directional_pct",
    "enhancements", "vol", "macro", "regime_grade_obj",
    "backtest", "recency_weights", "breaker",
}


@pytest.mark.parametrize("symbol", SMOKE_SYMBOLS)
@pytest.mark.parametrize("combo_name,combo_kwargs", TOGGLE_COMBOS)
def test_analyse_one_smoke(symbol: str, combo_name: str, combo_kwargs: dict):
    """Run `analyse_one(symbol, **combo)` and assert the result is well-formed.

    This is the headless equivalent of "click each stock on every page with
    each toggle on". If this passes for both a US and an ASX ticker across
    all 7 toggle combos, the per-stock pipeline is sound and any UI
    breakage will only ever be cosmetic.
    """
    from app_pipeline import analyse_one

    res = analyse_one(symbol, broker="Stake", enh_label=combo_name, **combo_kwargs)

    assert "error" not in res, f"{symbol} ({combo_name}) returned error: {res.get('error')}"
    missing = REQUIRED_RESULT_KEYS - set(res.keys())
    assert not missing, f"{symbol} ({combo_name}) missing result keys: {missing}"

    assert res["symbol"] == symbol
    assert res["spot_aud"] > 0, "spot price must be positive"
    assert res["signal"] in ("GO", "WAIT", "AVOID"), f"bad signal: {res['signal']}"
    assert res["trust_grade"] in ("A", "B", "C", "D", "F"), f"bad grade: {res['trust_grade']}"
    assert 0 <= res["trust_score"] <= 100, f"bad trust score: {res['trust_score']}"
    assert res["regime"] in ("bull", "bear", "sideways"), f"bad regime: {res['regime']}"

    # Forecast must have the right shape and properly-ordered bands.
    f = res["forecast"]
    assert len(f.forecast_mean) == len(f.forecast_lower) == len(f.forecast_upper)
    assert all(lo <= mid <= hi for lo, mid, hi in zip(
        f.forecast_lower, f.forecast_mean, f.forecast_upper
    )), "forecast bands not properly ordered"

    # Toggle-specific expectations: the diagnostic object should appear iff
    # its toggle is on.
    if combo_kwargs.get("enh_garch"):
        assert res["vol"] is not None, "GARCH on -> vol object expected"
    else:
        assert res["vol"] is None, "GARCH off -> vol must be None"

    if combo_kwargs.get("enh_macro"):
        assert res["macro"] is not None, "Macro on -> macro snapshot expected"
    else:
        assert res["macro"] is None

    if combo_kwargs.get("enh_regime_grade"):
        assert res["regime_grade_obj"] is not None, "Regime-grade on -> object expected"
    else:
        assert res["regime_grade_obj"] is None

    if combo_kwargs.get("enh_recency_weighted"):
        assert res["recency_weights"] is not None, "Recency on -> weights expected"
        weights = res["recency_weights"].weights
        assert abs(sum(weights.values()) - 1.0) < 1e-6, "weights must sum to 1"
    else:
        assert res["recency_weights"] is None

    if combo_kwargs.get("enh_drawdown_breaker"):
        assert res["breaker"] is not None, "Breaker on -> status expected"
    else:
        assert res["breaker"] is None


# =====================================================================
# Whole-watchlist smoke
# =====================================================================

def test_analyse_all_runs_clean_for_full_watchlist():
    """`analyse_all` with vanilla toggles must succeed for every symbol that
    has a local cache. Symbols without a cache are tolerated (they appear
    in the result list with an `error` field, the run as a whole still
    passes). This is the safety net for the Dashboard / Forward Outlook /
    Today's Playbook pages - they all source their data through this call.
    """
    from app_pipeline import analyse_all
    from core.tickers import WATCHLIST

    rows = analyse_all(broker="Stake", enh=all_off())
    assert len(rows) == len(WATCHLIST), "analyse_all dropped a symbol"

    cache_present = [t.symbol for t in WATCHLIST if _has_local_cache(t.symbol)]
    failures = [
        f"{r['symbol']}: {r['error']}"
        for r in rows
        if r.get("symbol") in cache_present and "error" in r
    ]
    assert not failures, (
        "analyse_all failed for cached symbols (these have data, so should "
        "not error):\n" + "\n".join(failures)
    )
