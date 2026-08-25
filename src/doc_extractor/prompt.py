"""Prompt builders for text and vision invoice extraction."""

import base64
from typing import Any

from doc_extractor.prompt_store import get_current

_USER_INSTRUCTION = (
    "Extract the invoice into the structured schema. "
    "Fill every field you can ground in the document."
)


def get_system_prompt() -> str:
    """Current system prompt from the file-backed registry."""
    return get_current()["system_prompt"]


def get_prompt_version() -> str:
    """Current version label (vN) from the file-backed registry."""
    return get_current()["version"]


def prompt_sha256() -> str:
    """Content hash so an un-bumped prompt edit is still visible in eval artifacts."""
    return get_current()["hash"]


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
