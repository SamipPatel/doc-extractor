"""File-backed prompt version registry.

The UI cannot rewrite Python source, so SYSTEM_PROMPT lives in JSON at the
repo root. Extraction and evals load the current entry at call time (like
reading a config file, not a compiled constant).
"""

import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Walk up from this module so the registry stays at the repo root even when
# doc_extractor is installed from src/ (editable) rather than as a wheel path.
def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "evals").is_dir():
            return parent
    raise RuntimeError("Cannot locate repo root for prompt registry")


DEFAULT_REGISTRY_PATH = _repo_root() / "prompts" / "registry.json"

# Used only when the registry file is missing (fresh clone / first load).
SEED_VERSION = "v2"
SEED_SYSTEM_PROMPT = """\
You extract structured invoice data from documents.

Rules:
- Use only information present in the document. Do not invent vendors, customers, \
line items, or amounts.
- If a field is missing or illegible, use null for optional fields; for required \
fields, use the best grounded value available in the document.
- Currency must be a 3-letter ISO-4217 code (default USD when implied).
- Dates must be ISO format YYYY-MM-DD.
- Money fields are decimal numbers without currency symbols.
- Preserve line-item order as shown on the invoice.
- subtotal is the sum of line-item amounts only. Do not add or subtract \
discount, tax, or shipping.
- total is subtotal minus discount, plus tax, plus shipping.
"""

_VERSION_RE = re.compile(r"^v(\d+)$")
_io_lock = threading.Lock()


def hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_prompt(text: str) -> str:
    # Editors disagree on trailing newlines; don't burn a version on that.
    return text.replace("\r\n", "\n").rstrip() + "\n"


def next_version(current: str) -> str:
    match = _VERSION_RE.match(current)
    if not match:
        raise ValueError(f"Cannot bump non-vN version label: {current!r}")
    return f"v{int(match.group(1)) + 1}"


def _write(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def _seed(path: Path) -> dict[str, Any]:
    registry = {
        "current": SEED_VERSION,
        "versions": {
            SEED_VERSION: {
                "system_prompt": SEED_SYSTEM_PROMPT,
                "created_at": datetime.now(UTC).isoformat(),
                "hash": hash_prompt(SEED_SYSTEM_PROMPT),
            }
        },
    }
    _write(path, registry)
    return registry


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path if path is not None else DEFAULT_REGISTRY_PATH
    with _io_lock:
        if not target.exists():
            return _seed(target)
        return json.loads(target.read_text(encoding="utf-8"))


def _version_sort_key(version: str) -> tuple[int, str]:
    match = _VERSION_RE.match(version)
    if match:
        return (int(match.group(1)), version)
    return (-1, version)


def get_current(path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    version = registry["current"]
    entry = registry["versions"][version]
    return {
        "version": version,
        "system_prompt": entry["system_prompt"],
        "hash": entry["hash"],
        "created_at": entry["created_at"],
    }


def get_version(version: str, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    entry = registry["versions"].get(version)
    if entry is None:
        raise KeyError(version)
    return {
        "version": version,
        "system_prompt": entry["system_prompt"],
        "hash": entry["hash"],
        "created_at": entry["created_at"],
        "is_current": version == registry["current"],
    }


def list_versions(path: Path | None = None) -> list[dict[str, Any]]:
    registry = load_registry(path)
    current = registry["current"]
    items = [
        {
            "version": version,
            "hash": entry["hash"],
            "created_at": entry["created_at"],
            "is_current": version == current,
        }
        for version, entry in registry["versions"].items()
    ]
    items.sort(key=lambda item: _version_sort_key(item["version"]), reverse=True)
    return items


def save_prompt(system_prompt: str, *, path: Path | None = None) -> dict[str, Any]:
    """Append a new version when text changes; no-op when it does not."""
    target = path if path is not None else DEFAULT_REGISTRY_PATH
    normalized = normalize_prompt(system_prompt)
    if not normalized.strip():
        raise ValueError("system_prompt is empty")

    with _io_lock:
        if target.exists():
            registry = json.loads(target.read_text(encoding="utf-8"))
        else:
            registry = _seed(target)

        current = registry["current"]
        current_entry = registry["versions"][current]
        if normalize_prompt(current_entry["system_prompt"]) == normalized:
            return {
                "unchanged": True,
                "version": current,
                "hash": current_entry["hash"],
                "system_prompt": current_entry["system_prompt"],
                "created_at": current_entry["created_at"],
            }

        new_version = next_version(current)
        entry = {
            "system_prompt": normalized,
            "created_at": datetime.now(UTC).isoformat(),
            "hash": hash_prompt(normalized),
        }
        registry["versions"][new_version] = entry
        registry["current"] = new_version
        _write(target, registry)

    return {
        "unchanged": False,
        "version": new_version,
        "hash": entry["hash"],
        "system_prompt": normalized,
        "created_at": entry["created_at"],
    }
