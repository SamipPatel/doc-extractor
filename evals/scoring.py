"""Field-level scoring of extracted invoices against ground truth.

Dates and amounts are exact after a format normalize (ISO / Decimal). Vendor
names get a looser normalize (case, whitespace, punctuation) because letterheads
vary in those ways without changing identity. Other strings stay exact after
trim so identifiers like '#85080' do not collapse to '85080'.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Table / aggregate order. Line-item keys here are collapsed (no index);
# per-doc results keep line_items[i].* so a mismatch is locatable.
FIELD_ORDER = [
    "vendor.name",
    "vendor.address",
    "vendor.phone",
    "vendor.email",
    "customer.name",
    "customer.address",
    "customer.contact",
    "invoice_number",
    "po_number",
    "invoice_date",
    "due_date",
    "terms",
    "currency",
    "line_items.description",
    "line_items.quantity",
    "line_items.unit_price",
    "line_items.amount",
    "subtotal",
    "discount",
    "tax_rate",
    "tax",
    "shipping",
    "total",
    "notes",
]

_VENDOR_STRING_FIELDS = ("address", "phone", "email")
_CUSTOMER_STRING_FIELDS = ("name", "address", "contact")
_INVOICE_STRING_FIELDS = (
    "invoice_number",
    "po_number",
    "terms",
    "currency",
    "notes",
)
_DATE_FIELDS = ("invoice_date", "due_date")
_AMOUNT_FIELDS = (
    "subtotal",
    "discount",
    "tax_rate",
    "tax",
    "shipping",
    "total",
)
_LINE_ITEM_STRING_FIELDS = ("description",)
_LINE_ITEM_AMOUNT_FIELDS = ("quantity", "unit_price", "amount")
_LINE_ITEM_INDEX_RE = re.compile(r"^line_items\[\d+\]\.")


def _missing(value: Any) -> bool:
    return value is None or value == ""


def _as_str(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    return None if text == "" else text


def _as_date(value: Any) -> date | None:
    if _missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def _as_amount(value: Any) -> Decimal | None:
    if _missing(value):
        return None
    return Decimal(str(value))


def normalize_vendor(value: Any) -> str:
    """Fold case/spacing/punctuation so 'Acme, Inc.' matches 'acme inc'."""
    if _missing(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def strings_match(predicted: Any, gold: Any) -> bool:
    return _as_str(predicted) == _as_str(gold)


def vendor_names_match(predicted: Any, gold: Any) -> bool:
    return normalize_vendor(predicted) == normalize_vendor(gold)


def dates_match(predicted: Any, gold: Any) -> bool:
    try:
        return _as_date(predicted) == _as_date(gold)
    except (TypeError, ValueError):
        return False


def amounts_match(predicted: Any, gold: Any) -> bool:
    # Decimal('1941') == Decimal('1941.00'); float would not be trustworthy here.
    try:
        return _as_amount(predicted) == _as_amount(gold)
    except (InvalidOperation, TypeError, ValueError):
        return False


def aggregate_field_name(field: str) -> str:
    """Collapse line_items[2].amount -> line_items.amount for per-field totals."""
    return _LINE_ITEM_INDEX_RE.sub("line_items.", field)


def score_document(predicted: dict[str, Any] | None, gold: dict[str, Any]) -> dict[str, bool]:
    """Return {field_path: correct} for one invoice.

    `predicted` is None when extraction failed: every gold field is a miss, and
    missing predicted line rows still count against line-item fields.
    """
    pred = predicted or {}
    results: dict[str, bool] = {}

    pred_vendor = pred.get("vendor") or {}
    gold_vendor = gold.get("vendor") or {}
    results["vendor.name"] = vendor_names_match(
        pred_vendor.get("name"), gold_vendor.get("name")
    )
    for key in _VENDOR_STRING_FIELDS:
        results[f"vendor.{key}"] = strings_match(
            pred_vendor.get(key), gold_vendor.get(key)
        )

    pred_customer = pred.get("customer") or {}
    gold_customer = gold.get("customer") or {}
    for key in _CUSTOMER_STRING_FIELDS:
        results[f"customer.{key}"] = strings_match(
            pred_customer.get(key), gold_customer.get(key)
        )

    for key in _INVOICE_STRING_FIELDS:
        results[key] = strings_match(pred.get(key), gold.get(key))
    for key in _DATE_FIELDS:
        results[key] = dates_match(pred.get(key), gold.get(key))
    for key in _AMOUNT_FIELDS:
        results[key] = amounts_match(pred.get(key), gold.get(key))

    # Index alignment: the prompt asks Claude to preserve printed order, so a
    # permutation is a miss rather than a Hungarian-matched credit.
    pred_items = pred.get("line_items") or []
    gold_items = gold.get("line_items") or []
    n_rows = max(len(pred_items), len(gold_items))
    for i in range(n_rows):
        pred_item = pred_items[i] if i < len(pred_items) else None
        gold_item = gold_items[i] if i < len(gold_items) else None
        if pred_item is None or gold_item is None:
            for key in (*_LINE_ITEM_STRING_FIELDS, *_LINE_ITEM_AMOUNT_FIELDS):
                results[f"line_items[{i}].{key}"] = False
            continue
        for key in _LINE_ITEM_STRING_FIELDS:
            results[f"line_items[{i}].{key}"] = strings_match(
                pred_item.get(key), gold_item.get(key)
            )
        for key in _LINE_ITEM_AMOUNT_FIELDS:
            results[f"line_items[{i}].{key}"] = amounts_match(
                pred_item.get(key), gold_item.get(key)
            )

    # Both-missing would otherwise look like a hit (null == null). A failed
    # extract should not get credit for fields the model never produced.
    if predicted is None:
        return {field: False for field in results}
    return results


def tally_fields(field_results: dict[str, bool]) -> dict[str, list[int]]:
    """Map aggregate field name -> [correct, compared]."""
    counts: dict[str, list[int]] = {}
    for field, correct in field_results.items():
        name = aggregate_field_name(field)
        bucket = counts.setdefault(name, [0, 0])
        bucket[1] += 1
        if correct:
            bucket[0] += 1
    return counts
