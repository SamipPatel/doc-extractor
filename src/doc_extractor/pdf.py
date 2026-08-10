"""PDF text extraction and page rendering for hybrid invoice intake."""

import re
from pathlib import Path

import pymupdf

# Non-whitespace character count below this triggers vision fallback.
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
    """Render each PDF page to PNG bytes."""
    path = Path(path)
    images: list[bytes] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
    return images


def needs_vision(text: str, threshold: int = VISION_TEXT_THRESHOLD) -> bool:
    """Return True when extracted text is too sparse for a text-only prompt."""
    compact = re.sub(r"\s+", "", text)
    return len(compact) < threshold
