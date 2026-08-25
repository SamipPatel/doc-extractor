"""Compare two eval-run artifacts (per-field / style / per-doc deltas)."""

import re
from typing import Any

from evals.scoring import FIELD_ORDER

_INDEXED = re.compile(r"^(\w+)\[(\d+)\]$")


def lookup_field(doc: dict[str, Any] | None, field: str) -> Any:
    """Resolve a scoring path like vendor.name or line_items[0].amount."""
    if doc is None:
        return None
    current: Any = doc
    for part in field.split("."):
        indexed = _INDEXED.match(part)
        if indexed:
            name, index_s = indexed.group(1), int(indexed.group(2))
            if not isinstance(current, dict):
                return None
            current = current.get(name)
            if not isinstance(current, list) or index_s >= len(current):
                return None
            current = current[index_s]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _meta(run: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "id": run_id,
        "timestamp": run.get("timestamp"),
        "prompt_version": run.get("prompt_version"),
        "prompt_hash": run.get("prompt_hash"),
        "model": run.get("model"),
        "total_cost_usd": run.get("total_cost_usd"),
        "n_docs": run.get("n_docs"),
        "n_errors": run.get("n_errors"),
        "overall_accuracy": run.get("overall_accuracy"),
        "overall_counts": run.get("overall_counts"),
    }


def _delta(b: float | None, a: float | None) -> float | None:
    if a is None or b is None:
        return None
    return b - a


def compare_runs(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    a_id: str,
    b_id: str,
) -> dict[str, Any]:
    """b minus a: positive delta means the newer (b) run improved."""
    per_field = []
    acc_a = a.get("per_field_accuracy") or {}
    acc_b = b.get("per_field_accuracy") or {}
    for field in FIELD_ORDER:
        if field not in acc_a and field not in acc_b:
            continue
        left = acc_a.get(field)
        right = acc_b.get(field)
        per_field.append(
            {
                "field": field,
                "a": left,
                "b": right,
                "delta": _delta(right, left),
            }
        )

    style_a = a.get("by_style") or {}
    style_b = b.get("by_style") or {}
    styles = list(dict.fromkeys([*style_a.keys(), *style_b.keys()]))
    by_style = [
        {
            "style": style,
            "a": style_a.get(style),
            "b": style_b.get(style),
            "delta": _delta(style_b.get(style), style_a.get(style)),
        }
        for style in styles
    ]

    docs_a = {doc["file"]: doc for doc in a.get("docs") or []}
    docs_b = {doc["file"]: doc for doc in b.get("docs") or []}
    improved: list[dict[str, Any]] = []
    regressed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    for filename in sorted(set(docs_a) & set(docs_b)):
        left = docs_a[filename]["accuracy"]
        right = docs_b[filename]["accuracy"]
        row = {
            "file": filename,
            "style": docs_b[filename].get("style") or docs_a[filename].get("style"),
            "a": left,
            "b": right,
            "delta": right - left,
        }
        if right > left:
            improved.append(row)
        elif right < left:
            regressed.append(row)
        else:
            unchanged.append(row)
    improved.sort(key=lambda row: row["delta"], reverse=True)
    regressed.sort(key=lambda row: row["delta"])

    return {
        "a": _meta(a, a_id),
        "b": _meta(b, b_id),
        "overall_delta": _delta(b.get("overall_accuracy"), a.get("overall_accuracy")),
        "per_field": per_field,
        "by_style": by_style,
        "improved": improved,
        "regressed": regressed,
        "unchanged_docs": len(unchanged),
    }
