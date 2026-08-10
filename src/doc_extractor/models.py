"""Pydantic models for structured invoice extraction."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Vendor(BaseModel):
    """The business that issued the invoice."""

    model_config = ConfigDict(extra="forbid")

    name: str
    address: str
    phone: str | None = None
    email: str | None = None


class Customer(BaseModel):
    """The bill-to party on the invoice."""

    model_config = ConfigDict(extra="forbid")

    name: str
    address: str
    contact: str | None = None


class LineItem(BaseModel):
    """A single billed product or service line."""

    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class Invoice(BaseModel):
    """Structured data extracted from an invoice document.

    """

    model_config = ConfigDict(extra="forbid")

    vendor: Vendor
    customer: Customer
    invoice_number: str
    po_number: str | None = None
    invoice_date: date
    due_date: date | None = None
    terms: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: list[LineItem]
    subtotal: Decimal
    discount: Decimal = Decimal(0)
    tax_rate: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    shipping: Decimal = Decimal(0)
    total: Decimal
    notes: str | None = None
