"""PDF text extraction and page rendering for hybrid invoice intake."""

import re
from pathlib import Path

import pymupdf

# Heuristic: below this many non-whitespace chars, treat as scan/image and use vision.
VISION_TEXT_THRESHOLD = 80


def extract_text(path: Path | str) -> str:
    """Extract concatenated text from all pages of a PDF."""
    path = Path(path)
    parts: list[str] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts)


def render_pages(path: Path | str, dpi: int = 150) -> list[bytes]:
    """Render each PDF page to PNG bytes.

    150 DPI balances OCR/vision readability against image size (and thus tokens).
    """
    path = Path(path)
    images: list[bytes] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
    return images


def needs_vision(text: str, threshold: int = VISION_TEXT_THRESHOLD) -> bool:
    """Return True when extracted text is too sparse for a text-only prompt."""
    # Strip whitespace so padded/near-empty PDFs don't look "rich" in text.
    compact = re.sub(r"\s+", "", text)
    return len(compact) < threshold
