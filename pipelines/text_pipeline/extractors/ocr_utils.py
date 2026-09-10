"""
OCR and Image Text Extraction Utilities.
Provides optical character recognition for embedded screenshots, scanned pages,
diagrams, and figures inside PDF and DOCX documents.
"""

import io
import re
from typing import Optional

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def is_ocr_available() -> bool:
    """Returns True if both Pillow and pytesseract are available."""
    return OCR_AVAILABLE


def extract_text_from_image_bytes(image_bytes: bytes, min_length: int = 5) -> str:
    """
    Extracts text from raw image bytes using Tesseract OCR.

    Args:
        image_bytes: Binary image content (PNG, JPEG, TIFF, BMP, etc.)
        min_length: Minimum meaningful text length to return.

    Returns:
        Extracted text or empty string if no text detected / OCR fails.
    """
    if not OCR_AVAILABLE or not image_bytes:
        return ""

    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Convert paletted or RGBA to RGB for robust OCR
        if image.mode in ("P", "RGBA", "LA"):
            image = image.convert("RGB")

        # Skip tiny thumbnail/icon images (e.g., bullet dots, logos < 50x50)
        if image.width < 50 or image.height < 50:
            return ""

        raw_text = pytesseract.image_to_string(image)
        cleaned_text = clean_ocr_text(raw_text)

        if len(cleaned_text.strip()) >= min_length:
            return cleaned_text.strip()
        return ""
    except Exception:
        # Gracefully handle unreadable or corrupted image streams
        return ""


def clean_ocr_text(raw_text: str) -> str:
    """Normalizes whitespace and removes excessive artifacts from OCR text."""
    if not raw_text:
        return ""
    # Normalize multiple newlines and spaces
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    # Remove excessive repeated punctuation symbols common in OCR noise
    cleaned = re.sub(r"([~`|_\-=*#])\1{4,}", "", cleaned)
    return cleaned.strip()
