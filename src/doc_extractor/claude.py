"""Anthropic client wrapper for structured invoice extraction."""

import os
from functools import lru_cache
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from doc_extractor.models import Invoice
from doc_extractor.prompt import SYSTEM_PROMPT
from doc_extractor.usage_log import instrument

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS = 4096


# Cache size 1 = process-wide singleton so instrument() wraps the client once.
@lru_cache(maxsize=1)
def get_client() -> Anthropic:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return instrument(Anthropic(api_key=api_key))


def extract_invoice_structured(
    content: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Invoice:
    """Call Claude with structured outputs and return a validated Invoice."""
    client = get_client()
    # messages.parse + output_format binds the reply to our Pydantic Invoice schema.
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_format=Invoice,
    )
    invoice = response.parsed_output
    # Fail closed: a null parse means we cannot trust downstream validation.
    if invoice is None:
        raise RuntimeError("Claude returned no structured invoice output")
    return invoice
