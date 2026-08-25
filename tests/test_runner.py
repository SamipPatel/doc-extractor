"""Eval runner table formatting and artifact persistence (no live API)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from evals.runner import format_table, run_eval
from doc_extractor.models import Customer, Invoice, LineItem, Vendor


def _sample_eval(tmp_path: Path) -> tuple[Path, Path, Invoice]:
    test_dir = tmp_path / "data"
    out_dir = tmp_path / "eval_runs"
    test_dir.mkdir()
    gold = {
        "vendor": {
            "name": "Acme Inc",
            "address": "1 Main",
            "phone": None,
            "email": None,
        },
        "customer": {
            "name": "Buyer",
            "address": "2 Oak",
            "contact": None,
        },
        "invoice_number": "1",
        "po_number": None,
        "invoice_date": "2026-04-08",
        "due_date": None,
        "terms": None,
        "currency": "USD",
        "line_items": [
            {
                "description": "Widget",
                "quantity": 1,
                "unit_price": 10,
                "amount": 10,
            }
        ],
        "subtotal": 10,
        "discount": 0,
        "tax_rate": 0,
        "tax": 0,
        "shipping": 0,
        "total": 10,
        "notes": None,
        "file": "invoice.pdf",
        "style": "clean",
        "layout": "layout_grid",
    }
    (test_dir / "ground_truth.json").write_text(json.dumps([gold]), encoding="utf-8")
    invoice = Invoice(
        vendor=Vendor(name="Acme Inc", address="1 Main"),
        customer=Customer(name="Buyer", address="2 Oak"),
        invoice_number="1",
        invoice_date=date(2026, 4, 8),
        line_items=[
            LineItem(
                description="Widget",
                quantity=Decimal(1),
                unit_price=Decimal(10),
                amount=Decimal(10),
            )
        ],
        subtotal=Decimal(10),
        total=Decimal(10),
    )
    return test_dir, out_dir, invoice


def test_format_table_includes_run_metadata_and_overall() -> None:
    table = format_table(
        {
            "timestamp": "2026-08-25T21:08:00+00:00",
            "prompt_version": "v1",
            "model": "claude-sonnet-4-5",
            "total_cost_usd": 0.4231,
            "n_docs": 34,
            "n_errors": 1,
            "per_field_counts": {"vendor.name": [32, 34], "total": [31, 34]},
            "overall_counts": [890, 1020],
            "by_style": {"clean": 0.951, "scanned": 0.88},
        }
    )
    assert "prompt=v1" in table
    assert "cost=$0.4231" in table
    assert "n=34" in table
    assert "errors=1" in table
    assert "vendor.name" in table
    assert "32/34" in table
    assert "OVERALL" in table
    assert "890/1020" in table
    assert "clean=95.1%" in table
    assert "scanned=88.0%" in table


def test_run_eval_writes_timestamped_artifact(tmp_path: Path, capsys) -> None:
    test_dir, out_dir, invoice = _sample_eval(tmp_path)

    with patch("evals.runner.extract_invoice", return_value=invoice):
        run = run_eval(test_dir=test_dir, out_dir=out_dir)

    assert run["prompt_version"] == "v2"
    assert run["system_prompt"]
    assert run["n_docs"] == 1
    assert run["n_errors"] == 0
    assert run["overall_accuracy"] == 1.0
    artifacts = list(out_dir.glob("run_*_v2.json"))
    assert len(artifacts) == 1
    saved = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert saved["docs"][0]["file"] == "invoice.pdf"
    assert "prompt_hash" in saved
    assert "system_prompt" in saved
    assert "artifact" not in saved
    assert run["artifact"] == artifacts[0].name
    assert "OVERALL" in capsys.readouterr().out


def test_run_eval_quiet_skips_stdout(tmp_path: Path, capsys) -> None:
    test_dir, out_dir, invoice = _sample_eval(tmp_path)
    with patch("evals.runner.extract_invoice", return_value=invoice):
        run_eval(test_dir=test_dir, out_dir=out_dir, quiet=True)
    assert capsys.readouterr().out == ""


def test_run_eval_progress_callback(tmp_path: Path) -> None:
    test_dir, out_dir, invoice = _sample_eval(tmp_path)
    events: list[dict] = []
    with patch("evals.runner.extract_invoice", return_value=invoice):
        run_eval(
            test_dir=test_dir,
            out_dir=out_dir,
            quiet=True,
            progress=events.append,
        )
    assert events[0]["done"] == 0
    assert events[0]["current_file"] == "invoice.pdf"
    assert events[-1]["done"] == 1
    assert events[-1]["total"] == 1
