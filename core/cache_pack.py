"""Build and validate portable cache packs for local browser/session restore.

The pack lets users export local cache state as a signed zip file and import it
in the next session. Every entry carries checksum + metadata checks, plus a hard
max age gate to prevent accidentally reusing stale cache state.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.backtest_cache import CACHE_DIR as BACKTEST_CACHE_DIR
from core.backtest_cache import BACKTEST_CACHE_TTL_HOURS, CACHE_VERSION as BACKTEST_CACHE_VERSION
from core.data import CACHE_DIR as DATA_CACHE_DIR
from core.data import CACHE_TTL_HOURS as DATA_CACHE_TTL_HOURS
from core.pipeline_cache import CACHE_DIR as PIPELINE_CACHE_DIR
from core.pipeline_cache import CACHE_VERSION as PIPELINE_CACHE_VERSION
from core.pipeline_cache import PIPELINE_CACHE_TTL_HOURS
from core.tickers import WATCHLIST

logger = logging.getLogger(__name__)

CACHE_PACK_SCHEMA_VERSION = 1
DEFAULT_PACK_MAX_AGE_HOURS = 168  # one week max age by default


def _pack_path_root(path: Path) -> str | None:
    """Map a cache file path into a zip path prefix."""
    resolved = path.resolve()
    data_root = DATA_CACHE_DIR.resolve()
    pipeline_root = PIPELINE_CACHE_DIR.resolve()
    backtest_root = BACKTEST_CACHE_DIR.resolve()

    try:
        if resolved.is_relative_to(data_root):
            rel = resolved.relative_to(data_root)
            return str(Path("data_cache") / rel)
        if resolved.is_relative_to(pipeline_root):
            rel = resolved.relative_to(pipeline_root)
            return str(Path("pipeline_cache") / rel)
        if resolved.is_relative_to(backtest_root):
            rel = resolved.relative_to(backtest_root)
            return str(Path("backtest_cache") / rel)
    except Exception:
        return None
    return None


def _collect_cache_files() -> list[Path]:
    files: list[Path] = []
    for root in (DATA_CACHE_DIR, PIPELINE_CACHE_DIR, BACKTEST_CACHE_DIR):
        if not root.exists():
            continue
        files.extend(sorted([p for p in root.glob("*.parquet")]))
        files.extend(sorted([p for p in root.glob("*.pkl")]))
        files.extend(sorted(root.glob("*.json")))
    return files


def build_cache_pack_bytes() -> tuple[bytes, dict[str, Any]]:
    """Create a zip containing current cache and strict metadata."""
    files = _collect_cache_files()
    manifest: dict[str, Any] = {
        "schema_version": CACHE_PACK_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at_epoch": int(time.time()),
        "required_symbols": [t.symbol for t in WATCHLIST],
        "payload": {
            "data_cache_ttl_hours": DATA_CACHE_TTL_HOURS,
            "pipeline_cache_ttl_hours": PIPELINE_CACHE_TTL_HOURS,
            "backtest_cache_ttl_hours": BACKTEST_CACHE_TTL_HOURS,
            "pipeline_cache_version": PIPELINE_CACHE_VERSION,
            "backtest_cache_version": BACKTEST_CACHE_VERSION,
        },
        "entries": [],
    }

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in files:
            arc = _pack_path_root(p)
            if arc is None:
                continue
            payload = p.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            zf.writestr(arc, payload)
            manifest["entries"].append({
                "arc": arc,
                "size": len(payload),
                "sha256": digest,
                "mtime": p.stat().st_mtime,
            })
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return stream.getvalue(), manifest


def _validate_manifest(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return `(errors, warnings)` from manifest metadata checks."""
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != CACHE_PACK_SCHEMA_VERSION:
        errors.append("Manifest schema is not supported.")
    required = {
        "generated_at_utc",
        "generated_at_epoch",
        "required_symbols",
        "payload",
        "entries",
    }
    missing = required - set(manifest.keys())
    if missing:
        errors.append(f"Manifest missing keys: {', '.join(sorted(missing))}.")
    payload = manifest.get("payload", {})
    if not isinstance(payload, dict):
        errors.append("Manifest payload missing.")
        return errors
    if payload.get("pipeline_cache_version") != PIPELINE_CACHE_VERSION:
        errors.append("Pack pipeline cache version does not match this app.")
    if payload.get("backtest_cache_version") != BACKTEST_CACHE_VERSION:
        errors.append("Pack backtest cache version does not match this app.")
    required_symbols = set(str(sym) for sym in manifest.get("required_symbols", []))
    current_symbols = set(t.symbol for t in WATCHLIST)
    if not required_symbols.issubset(current_symbols):
        errors.append("Pack includes symbols not on this watchlist configuration.")
    else:
        missing_symbols = sorted(current_symbols - required_symbols)
        if missing_symbols:
            warnings.append(
                f"Pack is incomplete for this watchlist: missing {', '.join(missing_symbols[:5])}"
            )
    entries = manifest.get("entries", [])
    if not isinstance(entries, list) or not entries:
        errors.append("Manifest has no cache entries.")
    return errors, warnings


def validate_cache_pack_bytes(
    payload: bytes,
    *,
    max_age_hours: int = DEFAULT_PACK_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Validate a cache pack payload before restoring.

    Returns `{valid: bool, warnings: [...], errors: [...], manifest: {...}}`.
    """
    out: dict[str, Any] = {
        "valid": False,
        "warnings": [],
        "errors": [],
        "manifest": {},
    }
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            raw = zf.read("manifest.json")
    except Exception as e:
        out["errors"].append(f"Could not read zip payload: {e}")
        return out

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as e:
        out["errors"].append(f"Manifest is not valid JSON: {e}")
        return out

    payload_config = manifest.get("payload", {})
    out["manifest"] = manifest
    _errors, _warnings = _validate_manifest(manifest)
    out["errors"].extend(_errors)
    out["warnings"].extend(_warnings)

    now = time.time()
    generated = manifest.get("generated_at_epoch")
    if not isinstance(generated, int):
        out["errors"].append("Manifest age field is missing.")
    else:
        age_hours = (now - generated) / 3600
        if age_hours < 0:
            out["warnings"].append("Pack timestamp is in the future.")
        elif age_hours > max_age_hours:
            out["errors"].append(
                f"Pack is too old ({age_hours:.1f}h > {max_age_hours}h)."
            )
        out["age_hours"] = round(age_hours, 2)

    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            entries = manifest.get("entries", [])
            if isinstance(entries, list):
                for item in entries:
                    if not isinstance(item, dict):
                        out["errors"].append("Manifest entry is malformed.")
                        continue
                    arc = item.get("arc")
                    expected_sha = item.get("sha256")
                    source_mtime = item.get("mtime")
                    if not isinstance(arc, str) or not isinstance(expected_sha, str):
                        out["errors"].append("Manifest entry missing file hash.")
                        continue
                    try:
                        actual = hashlib.sha256(zf.read(arc)).hexdigest()
                    except KeyError:
                        out["errors"].append(f"Missing file in zip: {arc}")
                        continue
                    if actual != expected_sha:
                        out["errors"].append(f"Checksum mismatch for {arc}")
                    if isinstance(source_mtime, (int, float)):
                        ttl = payload_config.get("pipeline_cache_ttl_hours", PIPELINE_CACHE_TTL_HOURS)
                        if arc.startswith("pipeline_cache/"):
                            ttl = payload_config.get("pipeline_cache_ttl_hours", ttl)
                        elif arc.startswith("backtest_cache/"):
                            ttl = payload_config.get("backtest_cache_ttl_hours", ttl)
                        elif arc.startswith("data_cache/"):
                            ttl = payload_config.get("data_cache_ttl_hours", ttl)
                        age_hours = (now - float(source_mtime)) / 3600
                        if age_hours > float(ttl) + 1e-9:
                            out["warnings"].append(f"{arc} is older than its source cache TTL ({age_hours:.1f}h)")
    except Exception as e:
        out["errors"].append(f"Failed checksum validation: {e}")

    out["valid"] = len(out["errors"]) == 0
    return out


def restore_cache_pack_bytes(payload: bytes, *, overwrite: bool = True) -> dict[str, Any]:
    """Restore cache files from a pack after validation."""
    status = validate_cache_pack_bytes(payload)
    result = {
        "ok": False,
        "restored": 0,
        "manifest": status.get("manifest", {}),
        "warnings": status.get("warnings", []),
        "errors": status.get("errors", []),
    }
    if not status["valid"]:
        return result

    manifest = status["manifest"]
    if not isinstance(manifest, dict):
        result["errors"].append("Manifest unavailable.")
        return result
    entries = manifest.get("entries", [])
    restored = 0
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        for item in entries:
            if not isinstance(item, dict):
                continue
            arc = item.get("arc")
            if not isinstance(arc, str):
                continue
            arc_parts = Path(arc).parts
            if len(arc_parts) < 2:
                result["errors"].append(f"Invalid path in manifest: {arc}")
                continue
            if ".." in arc_parts:
                result["errors"].append(f"Unsafe path blocked: {arc}")
                continue
            root = arc_parts[0]
            rel = Path(*arc_parts[1:])
            if root == "data_cache":
                target = DATA_CACHE_DIR / rel
            elif root == "pipeline_cache":
                target = PIPELINE_CACHE_DIR / rel
            elif root == "backtest_cache":
                target = BACKTEST_CACHE_DIR / rel
            else:
                result["errors"].append(f"Unknown destination for {arc}")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and not overwrite:
                    continue
                target.write_bytes(zf.read(arc))
                restored += 1
                logger.info("Restored %s", target)
            except Exception as e:
                result["errors"].append(f"Failed writing {arc}: {e}")

    result["ok"] = len(result["errors"]) == 0
    result["restored"] = restored
    return result

