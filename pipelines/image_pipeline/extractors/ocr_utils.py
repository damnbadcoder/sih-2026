"""
Deterministic OCR fallback utility for diagram node validation.
"""
from typing import List, Dict, Any


class ImageOCRUtils:
    """Provides OCR extraction helpers for image pipelines."""

    @staticmethod
    def extract_ocr_ground_truth(image_bytes: bytes) -> List[Dict[str, Any]]:
        """Extracts OCR text strings when EasyOCR is installed."""
        try:
            import easyocr  # type: ignore
            reader = easyocr.Reader(['en'], gpu=False)
            results = reader.readtext(image_bytes)
            return [{"text": item[1], "confidence": float(item[2])} for item in results]
        except Exception:
            return []
