"""Prompt builders for text and vision invoice extraction."""

import base64
import hashlib
from typing import Any

SYSTEM_PROMPT = """\
You extract structured invoice data from documents.

Rules:
- Use only information present in the document. Do not invent vendors, customers, \
line items, or amounts.
- If a field is missing or illegible, use null for optional fields; for required \
fields, use the best grounded value available in the document.
- Currency must be a 3-letter ISO-4217 code (default USD when implied).
- Dates must be ISO format YYYY-MM-DD.
- Money fields are decimal numbers without currency symbols.
- Preserve line-item order as shown on the invoice.
- subtotal is the sum of line-item amounts only. Do not add or subtract \
discount, tax, or shipping.
- total is subtotal minus discount, plus tax, plus shipping.
"""

# Bump when SYSTEM_PROMPT changes in a way that should distinguish eval runs.
PROMPT_VERSION = "v2"

_USER_INSTRUCTION = (
    "Extract the invoice into the structured schema. "
    "Fill every field you can ground in the document."
)


def prompt_sha256() -> str:
    """Content hash so an un-bumped prompt edit is still visible in eval artifacts."""
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def build_text_content(text: str) -> list[dict[str, Any]]:
    """Build user message content from extracted PDF text."""
    # XML-ish tags delimit document text so the model treats it as data, not instructions.
    return [
        {
            "type": "text",
            "text": (
                f"{_USER_INSTRUCTION}\n\n"
                f"<invoice_text>\n{text}\n</invoice_text>"
            ),
        }
    ]


def build_vision_content(page_images: list[bytes]) -> list[dict[str, Any]]:
    """Build user message content from rendered page PNGs."""
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{_USER_INSTRUCTION}\n\n"
                "The invoice pages follow as images in page order."
            ),
        }
    ]
    # Page order preserved: Claude sees pages as sequential image blocks (Anthropic vision format).
    for png in page_images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(png).decode("ascii"),
                },
            }
        )
    return content
