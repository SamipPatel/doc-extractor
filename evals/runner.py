"""Batch-evaluate extract_invoice() against test_data/ground_truth.json."""

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from doc_extractor.claude import DEFAULT_MODEL
from doc_extractor.pipeline import extract_invoice
from doc_extractor.prompt import get_prompt_version, get_system_prompt, prompt_sha256
from doc_extractor.usage_log import capturing_usage
from evals.scoring import FIELD_ORDER, score_document, tally_fields

# evals/ sits next to test_data/ and eval_runs/ at the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DIR = _REPO_ROOT / "test_data"
DEFAULT_OUT_DIR = _REPO_ROOT / "eval_runs"
_STYLE_ORDER = ("clean", "scanned", "handwritten", "downloaded")

ProgressFn = Callable[[dict[str, Any]], None]


def _ratio(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def _merge_counts(into: dict[str, list[int]], extra: dict[str, list[int]]) -> None:
    for name, (ok, n) in extra.items():
        bucket = into.setdefault(name, [0, 0])
        bucket[0] += ok
        bucket[1] += n


def _style_order(styles: set[str]) -> list[str]:
    known = [s for s in _STYLE_ORDER if s in styles]
    rest = sorted(styles - set(_STYLE_ORDER))
    return known + rest


def format_table(run: dict[str, Any]) -> str:
    lines = [
        (
            f"run    {run['timestamp']}   prompt={run['prompt_version']}   "
            f"model={run['model']}   cost=${run['total_cost_usd']:.4f}   "
            f"n={run['n_docs']}  errors={run['n_errors']}"
        ),
        f"{'field':<26} {'ok/n':>10} {'acc':>8}",
    ]
    counts: dict[str, list[int]] = run["per_field_counts"]
    for field in FIELD_ORDER:
        if field not in counts:
            continue
        ok, n = counts[field]
        lines.append(f"{field:<26} {f'{ok}/{n}':>10} {_ratio(ok, n) * 100:7.1f}%")
    ok, n = run["overall_counts"]
    lines.append(f"{'OVERALL':<26} {f'{ok}/{n}':>10} {_ratio(ok, n) * 100:7.1f}%")
    style_parts = [
        f"{style}={acc * 100:.1f}%" for style, acc in run["by_style"].items()
    ]
    lines.append("by style  " + "  ".join(style_parts))
    return "\n".join(lines)


def run_eval(
    *,
    test_dir: Path = DEFAULT_TEST_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    limit: int | None = None,
    progress: ProgressFn | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Score each ground-truth PDF and persist a timestamped run artifact."""
    gold_path = test_dir / "ground_truth.json"
    gold_docs: list[dict[str, Any]] = json.loads(gold_path.read_text(encoding="utf-8"))
    if limit is not None:
        gold_docs = gold_docs[:limit]

    # Snapshot at start so a mid-run registry bump cannot mix versions in one artifact.
    prompt_version = get_prompt_version()
    system_prompt = get_system_prompt()
    prompt_hash = prompt_sha256()

    started = datetime.now(UTC)
    per_field_counts: dict[str, list[int]] = {}
    style_counts: dict[str, list[int]] = {}
    docs: list[dict[str, Any]] = []
    n_errors = 0
    total = len(gold_docs)

    with capturing_usage() as all_costs:
        for index, gold in enumerate(gold_docs):
            filename = gold["file"]
            if progress is not None:
                progress(
                    {
                        "done": index,
                        "total": total,
                        "current_file": filename,
                        "n_errors": n_errors,
                    }
                )
            style = gold.get("style", "unknown")
            extracted: dict[str, Any] | None = None
            error: str | None = None
            with capturing_usage() as doc_costs:
                try:
                    invoice = extract_invoice(test_dir / filename)
                    extracted = invoice.model_dump(mode="json")
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    n_errors += 1

            field_results = score_document(extracted, gold)
            _merge_counts(per_field_counts, tally_fields(field_results))
            doc_ok = sum(field_results.values())
            doc_n = len(field_results)
            _merge_counts(style_counts, {style: [doc_ok, doc_n]})
            docs.append(
                {
                    "file": filename,
                    "style": style,
                    "ok": error is None,
                    "error": error,
                    "field_results": field_results,
                    "accuracy": _ratio(doc_ok, doc_n),
                    "extracted": extracted,
                    "cost_usd": round(sum(doc_costs), 6),
                }
            )

    if progress is not None:
        progress(
            {
                "done": total,
                "total": total,
                "current_file": None,
                "n_errors": n_errors,
            }
        )

    overall_ok = sum(ok for ok, _ in per_field_counts.values())
    overall_n = sum(n for _, n in per_field_counts.values())
    run = {
        "timestamp": started.isoformat(),
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "system_prompt": system_prompt,
        "model": DEFAULT_MODEL,
        "total_cost_usd": round(sum(all_costs), 6),
        "n_docs": len(docs),
        "n_errors": n_errors,
        "overall_accuracy": _ratio(overall_ok, overall_n),
        "overall_counts": [overall_ok, overall_n],
        "per_field_accuracy": {
            field: _ratio(*per_field_counts[field])
            for field in FIELD_ORDER
            if field in per_field_counts
        },
        "per_field_counts": {
            field: per_field_counts[field]
            for field in FIELD_ORDER
            if field in per_field_counts
        },
        "by_style": {
            style: _ratio(*style_counts[style])
            for style in _style_order(set(style_counts))
        },
        "docs": docs,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"run_{stamp}_{prompt_version}.json"
    out_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    run["artifact"] = out_path.name
    if not quiet:
        print(format_table(run))
        print(f"\nwrote {out_path}")
    return run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate invoice extraction against ground truth."
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=DEFAULT_TEST_DIR,
        help="Directory with ground_truth.json and PDFs",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for timestamped run JSON",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Score only the first N ground-truth rows (smoke runs)",
    )
    args = parser.parse_args(argv)
    try:
        run_eval(test_dir=args.test_dir, out_dir=args.out_dir, limit=args.limit)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
