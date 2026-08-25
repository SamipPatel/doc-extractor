"""Compare-run deltas and field path lookup."""

import pytest

from evals.compare import compare_runs, lookup_field


def test_lookup_field_nested_and_indexed():
    doc = {
        "vendor": {"name": "Acme"},
        "line_items": [{"amount": 10}, {"amount": 4}],
    }
    assert lookup_field(doc, "vendor.name") == "Acme"
    assert lookup_field(doc, "line_items[1].amount") == 4
    assert lookup_field(doc, "line_items[9].amount") is None
    assert lookup_field(None, "vendor.name") is None


def _run(version: str, overall: float, docs: list[dict]) -> dict:
    return {
        "timestamp": "2026-08-25T21:00:00+00:00",
        "prompt_version": version,
        "prompt_hash": "abc",
        "model": "claude-sonnet-4-5",
        "total_cost_usd": 0.1,
        "n_docs": len(docs),
        "n_errors": 0,
        "overall_accuracy": overall,
        "overall_counts": [1, 2],
        "per_field_accuracy": {"vendor.name": overall, "total": 1.0},
        "by_style": {"clean": overall},
        "docs": docs,
    }


def test_compare_runs_improved_and_regressed():
    a = _run(
        "v1",
        0.5,
        [
            {"file": "a.pdf", "style": "clean", "accuracy": 0.4},
            {"file": "b.pdf", "style": "clean", "accuracy": 0.8},
            {"file": "c.pdf", "style": "scanned", "accuracy": 0.5},
        ],
    )
    b = _run(
        "v2",
        0.7,
        [
            {"file": "a.pdf", "style": "clean", "accuracy": 0.9},
            {"file": "b.pdf", "style": "clean", "accuracy": 0.5},
            {"file": "c.pdf", "style": "scanned", "accuracy": 0.5},
        ],
    )
    result = compare_runs(a, b, a_id="run_a", b_id="run_b")
    assert result["overall_delta"] == pytest.approx(0.2)
    assert result["improved"][0]["file"] == "a.pdf"
    assert result["regressed"][0]["file"] == "b.pdf"
    assert result["unchanged_docs"] == 1
    name = next(row for row in result["per_field"] if row["field"] == "vendor.name")
    assert name["delta"] == pytest.approx(0.2)
