"""Domain validation for extracted invoices beyond Pydantic schema checks."""

from decimal import Decimal

from pydantic import ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

from doc_extractor.models import Invoice

TOLERANCE = Decimal("0.02")


def _approx_equal(a: Decimal, b: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def validate_invoice(invoice: Invoice, *, tolerance: Decimal = TOLERANCE) -> Invoice:
    """Raise ValidationError if arithmetic / domain rules fail; else return invoice."""
    errors: list[InitErrorDetails] = []

    if not invoice.line_items:
        errors.append(
            {
                "type": PydanticCustomError(
                    "empty_line_items",
                    "Invoice must have at least one line item",
                ),
                "loc": ("line_items",),
                "input": invoice.line_items,
            }
        )

    if invoice.total < 0:
        errors.append(
            {
                "type": PydanticCustomError(
                    "negative_total",
                    "Invoice total must be >= 0",
                ),
                "loc": ("total",),
                "input": invoice.total,
            }
        )

    for i, item in enumerate(invoice.line_items):
        expected = item.quantity * item.unit_price
        if not _approx_equal(item.amount, expected, tolerance):
            errors.append(
                {
                    "type": PydanticCustomError(
                        "line_amount_mismatch",
                        "amount {amount} != quantity * unit_price ({expected})",
                        {"amount": str(item.amount), "expected": str(expected)},
                    ),
                    "loc": ("line_items", i, "amount"),
                    "input": item.amount,
                }
            )

    line_sum = sum((item.amount for item in invoice.line_items), Decimal(0))
    expected_subtotal = line_sum - invoice.discount
    if not _approx_equal(invoice.subtotal, expected_subtotal, tolerance):
        errors.append(
            {
                "type": PydanticCustomError(
                    "subtotal_mismatch",
                    "subtotal {subtotal} != sum(line amounts) - discount ({expected})",
                    {
                        "subtotal": str(invoice.subtotal),
                        "expected": str(expected_subtotal),
                    },
                ),
                "loc": ("subtotal",),
                "input": invoice.subtotal,
            }
        )

    expected_total = invoice.subtotal + invoice.tax + invoice.shipping
    if not _approx_equal(invoice.total, expected_total, tolerance):
        errors.append(
            {
                "type": PydanticCustomError(
                    "total_mismatch",
                    "total {total} != subtotal + tax + shipping ({expected})",
                    {"total": str(invoice.total), "expected": str(expected_total)},
                ),
                "loc": ("total",),
                "input": invoice.total,
            }
        )

    if errors:
        raise ValidationError.from_exception_data("Invoice", errors)

    return invoice
