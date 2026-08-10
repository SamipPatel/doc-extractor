"""Prompt builders for text and vision invoice extraction."""

import base64
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
"""

_USER_INSTRUCTION = (
    "Extract the invoice into the structured schema. "
    "Fill every field you can ground in the document."
)


def build_text_content(text: str) -> list[dict[str, Any]]:
    """Build user message content from extracted PDF text."""
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
