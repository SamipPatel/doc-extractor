"""Scoring rules: date/amount exact after normalize, vendor name folded."""

from datetime import date

from evals.scoring import (
    amounts_match,
    dates_match,
    score_document,
    strings_match,
    tally_fields,
    vendor_names_match,
)

GOLD = {
    "vendor": {
        "name": "Hernandez & Sons Plumbing",
        "address": "732 Alamo Drive\nSan Antonio, TX 78205",
        "phone": "",
        "email": "office@hernandezplumbing.example.com",
    },
    "customer": {
        "name": "Harbor Point Dental",
        "address": "215 Bayview Ave\nAnnapolis, MD 21401",
        "contact": "",
    },
    "invoice_number": "#85080",
    "po_number": None,
    "invoice_date": "2026-04-08",
    "due_date": None,
    "terms": "",
    "currency": "USD",
    "line_items": [
        {
            "description": "Pipe replacement (per ft)",
            "quantity": 3,
            "unit_price": 17,
            "amount": 51,
        },
        {
            "description": "Labor",
            "quantity": 1,
            "unit_price": 100,
            "amount": 100,
        },
    ],
    "subtotal": 151,
    "discount": 0,
    "tax_rate": 6.25,
    "tax": 9.44,
    "shipping": 0,
    "total": 160.44,
    "notes": "",
    "file": "invoice_012_scanned.pdf",
    "style": "scanned",
    "layout": "layout_minimal",
}


def _pred(**overrides: object) -> dict:
    predicted = {
        "vendor": dict(GOLD["vendor"]),
        "customer": dict(GOLD["customer"]),
        "invoice_number": GOLD["invoice_number"],
        "po_number": GOLD["po_number"],
        "invoice_date": GOLD["invoice_date"],
        "due_date": GOLD["due_date"],
        "terms": GOLD["terms"],
        "currency": GOLD["currency"],
        "line_items": [dict(item) for item in GOLD["line_items"]],
        "subtotal": GOLD["subtotal"],
        "discount": GOLD["discount"],
        "tax_rate": GOLD["tax_rate"],
        "tax": GOLD["tax"],
        "shipping": GOLD["shipping"],
        "total": GOLD["total"],
        "notes": GOLD["notes"],
    }
    predicted.update(overrides)
    return predicted


def test_dates_match_after_iso_normalize() -> None:
    assert dates_match("2026-04-08", date(2026, 4, 8))
    assert dates_match("2026-04-08T00:00:00", "2026-04-08")
    assert not dates_match("2026-04-09", "2026-04-08")
    assert dates_match(None, "")
    assert not dates_match("2026-04-08", None)


def test_amounts_match_int_and_two_decimals() -> None:
    assert amounts_match(1941, 1941.00)
    assert amounts_match("51", 51)
    assert not amounts_match(51, 51.01)
    assert amounts_match(None, "")
    assert not amounts_match(0, None)


def test_vendor_name_ignores_case_whitespace_punctuation() -> None:
    assert vendor_names_match(
        "Hernandez & Sons Plumbing",
        "hernandez  sons plumbing",
    )
    assert vendor_names_match("Acme, Inc.", "acme inc")
    assert not vendor_names_match("Acme Inc", "Acme LLC")


def test_empty_string_matches_null_for_optional_strings() -> None:
    assert strings_match("", None)
    assert strings_match("  ", None)
    assert strings_match("Net 15", "Net 15")
    assert not strings_match("Net 15", "net 15")


def test_invoice_number_keeps_punctuation() -> None:
    results = score_document(_pred(invoice_number="85080"), GOLD)
    assert results["invoice_number"] is False
    results = score_document(_pred(invoice_number="#85080"), GOLD)
    assert results["invoice_number"] is True


def test_mismatched_line_item_counts_are_misses() -> None:
    predicted = _pred()
    predicted["line_items"] = [predicted["line_items"][0]]
    results = score_document(predicted, GOLD)
    assert results["line_items[0].description"] is True
    assert results["line_items[0].amount"] is True
    assert results["line_items[1].description"] is False
    assert results["line_items[1].quantity"] is False
    assert results["line_items[1].unit_price"] is False
    assert results["line_items[1].amount"] is False


def test_perfect_match_is_all_true() -> None:
    results = score_document(_pred(), GOLD)
    assert all(results.values())


def test_extra_predicted_line_item_is_miss() -> None:
    predicted = _pred()
    predicted["line_items"].append(
        {"description": "Extra", "quantity": 1, "unit_price": 1, "amount": 1}
    )
    results = score_document(predicted, GOLD)
    assert results["line_items[2].description"] is False
    assert results["line_items[2].amount"] is False
    assert results["line_items[0].description"] is True


def test_tally_collapses_line_item_indices() -> None:
    results = score_document(_pred(), GOLD)
    counts = tally_fields(results)
    assert counts["line_items.description"] == [2, 2]
    assert counts["vendor.name"] == [1, 1]
    assert "file" not in results
    assert "style" not in results


def test_failed_extraction_scores_all_gold_fields_wrong() -> None:
    results = score_document(None, GOLD)
    assert results["vendor.name"] is False
    assert results["invoice_date"] is False
    assert results["total"] is False
    assert results["line_items[0].amount"] is False
    assert results["line_items[1].description"] is False
    assert all(correct is False for correct in results.values())
