"""Domain arithmetic: subtotal is line items only; discount lands on total."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from doc_extractor.models import Customer, Invoice, LineItem, Vendor
from doc_extractor.validate import validate_invoice


def _invoice(**overrides: object) -> Invoice:
    data: dict[str, object] = {
        "vendor": Vendor(name="Acme", address="1 Main"),
        "customer": Customer(name="Buyer", address="2 Oak"),
        "invoice_number": "1",
        "invoice_date": date(2026, 4, 8),
        "line_items": [
            LineItem(
                description="A",
                quantity=Decimal(2),
                unit_price=Decimal("10.00"),
                amount=Decimal("20.00"),
            ),
            LineItem(
                description="B",
                quantity=Decimal(1),
                unit_price=Decimal("5.50"),
                amount=Decimal("5.50"),
            ),
        ],
        "subtotal": Decimal("25.50"),
        "discount": Decimal("2.00"),
        "tax": Decimal("1.50"),
        "shipping": Decimal("3.00"),
        "total": Decimal("28.00"),
    }
    data.update(overrides)
    return Invoice.model_validate(data)


def test_discounted_invoice_passes_when_subtotal_is_line_sum() -> None:
    invoice = _invoice()
    assert validate_invoice(invoice) is invoice


def test_subtotal_must_not_net_out_discount() -> None:
    # Old rule was subtotal == line_sum - discount; that should now fail.
    invoice = _invoice(subtotal=Decimal("23.50"), total=Decimal("26.00"))
    with pytest.raises(ValidationError, match="subtotal_mismatch"):
        validate_invoice(invoice)


def test_total_subtracts_discount() -> None:
    invoice = _invoice(total=Decimal("30.00"))
    with pytest.raises(ValidationError, match="total_mismatch"):
        validate_invoice(invoice)


def test_invoice_003_gold_math() -> None:
    invoice = _invoice(
        line_items=[
            LineItem(
                description="Server migration",
                quantity=Decimal(2),
                unit_price=Decimal("1485.25"),
                amount=Decimal("2970.5"),
            ),
            LineItem(
                description="Consulting hours",
                quantity=Decimal(2),
                unit_price=Decimal(173),
                amount=Decimal(346),
            ),
        ],
        subtotal=Decimal("3316.5"),
        discount=Decimal("165.83"),
        tax=Decimal("196.92"),
        shipping=Decimal(0),
        total=Decimal("3347.59"),
    )
    assert validate_invoice(invoice) is invoice
