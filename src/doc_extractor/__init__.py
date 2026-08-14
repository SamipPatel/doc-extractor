from doc_extractor.models import Customer, Invoice, LineItem, Vendor
from doc_extractor.pipeline import extract_invoice

# Explicit public surface (like index.ts named exports) — star-imports only get these.
__all__ = [
    "Customer",
    "Invoice",
    "LineItem",
    "Vendor",
    "extract_invoice",
]


def main() -> None:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Extract structured invoice data from a PDF."
    )
    parser.add_argument("pdf", type=str, help="Path to an invoice PDF")
    args = parser.parse_args()

    try:
        invoice = extract_invoice(args.pdf)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        # Chain with `from exc` so the original traceback stays available for debugging.
        raise SystemExit(1) from exc

    # mode="json" turns date/Decimal into JSON-safe types (ISO strings / numbers).
    print(json.dumps(invoice.model_dump(mode="json"), indent=2))
