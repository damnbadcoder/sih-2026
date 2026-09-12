"""
OCR and Image Text Extraction Utilities.
Provides OCR with automated image pre-processing, contrast normalization,
and multi-mode page segmentation to support slide infographics and diagrams.
"""

import io
import re
from typing import Optional

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def is_ocr_available() -> bool:
    """Returns True if both Pillow and pytesseract are available."""
    return OCR_AVAILABLE


def extract_text_from_image_bytes(image_bytes: bytes, min_length: int = 5, psm_mode: int = 6) -> str:
    """
    Extracts text from binary image content with contrast adjustment and adaptive PSM.

    Args:
        image_bytes: Binary image content.
        min_length: Minimum text length to qualify as a valid extraction.
        psm_mode: Tesseract Page Segmentation Mode (defaults to 6: Assume uniform text block).

    Returns:
        Extracted, cleaned text string.
    """
    if not OCR_AVAILABLE or not image_bytes:
        return ""

    try:
        image = Image.open(io.BytesIO(image_bytes))

        # Filter tiny icons or bullet decorations
        if image.width < 40 or image.height < 40:
            return ""

        # Preprocessing: convert to grayscale and boost contrast for slide infographics
        if image.mode != "L":
            image = image.convert("L")

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.8)

        # Primary extraction using specified PSM
        custom_config = f"--psm {psm_mode}"
        raw_text = pytesseract.image_to_string(image, config=custom_config)
        cleaned = clean_ocr_text(raw_text)

        # Secondary pass with sparse layout mode (PSM 11) if primary pass yields low return
        if len(cleaned) < min_length:
            raw_text_sparse = pytesseract.image_to_string(image, config="--psm 11")
            cleaned = clean_ocr_text(raw_text_sparse)

        return cleaned if len(cleaned) >= min_length else ""
    except Exception:
        return ""


def clean_ocr_text(raw_text: str) -> str:
    """Normalizes whitespace and strips non-printable OCR hallucination noise."""
    if not raw_text:
        return ""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    # Strip excessive repetitive character runs
    cleaned = re.sub(r"([~`|_\-=*#])\1{4,}", "", cleaned)
    return cleaned.strip()