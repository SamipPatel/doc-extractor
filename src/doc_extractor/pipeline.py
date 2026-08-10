"""Hybrid invoice extraction orchestration."""

from pathlib import Path

from doc_extractor.claude import extract_invoice_structured
from doc_extractor.models import Invoice
from doc_extractor.pdf import extract_text, needs_vision, render_pages
from doc_extractor.prompt import build_text_content, build_vision_content
from doc_extractor.usage_log import labeled
from doc_extractor.validate import validate_invoice


def extract_invoice(path: Path | str) -> Invoice:
    """Extract, structure, and validate an invoice from a PDF path."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    text = extract_text(path)
    if needs_vision(text):
        label = "extract-vision"
        content = build_vision_content(render_pages(path))
    else:
        label = "extract-text"
        content = build_text_content(text)

    with labeled(label):
        invoice = extract_invoice_structured(content)

    return validate_invoice(invoice)
