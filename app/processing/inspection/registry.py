from app.core.formats import (
    MEDIA_CATEGORY_AUDIO,
    MEDIA_CATEGORY_DOCUMENT,
    MEDIA_CATEGORY_IMAGE,
    MEDIA_CATEGORY_TEXT,
    MEDIA_CATEGORY_VIDEO,
    FormatClass,
)
from app.processing.inspection.audio import AudioInspector
from app.processing.inspection.base import ContentInspector
from app.processing.inspection.docx import DOCXInspector
from app.processing.inspection.image import ImageInspector
from app.processing.inspection.pdf import PDFInspector
from app.processing.inspection.spreadsheet import XLSXInspector
from app.processing.inspection.text import TextInspector
from app.processing.inspection.video import VideoInspector

_INSPECTORS: dict[str, list[ContentInspector]] = {
    MEDIA_CATEGORY_TEXT: [TextInspector()],
    MEDIA_CATEGORY_DOCUMENT: [PDFInspector(), DOCXInspector(), XLSXInspector()],
    MEDIA_CATEGORY_IMAGE: [ImageInspector()],
    MEDIA_CATEGORY_AUDIO: [AudioInspector()],
    MEDIA_CATEGORY_VIDEO: [VideoInspector()],
}


def register_inspector(inspector: ContentInspector) -> None:
    """Register an inspector under its declared media category."""
    _INSPECTORS.setdefault(inspector.media_category, []).append(inspector)


def get_inspector(classification: FormatClass | str) -> ContentInspector | None:
    """Resolve the inspector for ``classification``.

    Accepts a full :class:`FormatClass` for precise format-aware selection, or
    a bare media category for coarse routing. A category with several
    inspectors (e.g. ``document``) is ambiguous and yields ``None`` — callers
    looking for a specific inspector must pass a :class:`FormatClass`.
    """
    if isinstance(classification, str):
        candidates = _INSPECTORS.get(classification, [])
        return candidates[0] if len(candidates) == 1 else None

    for inspector in _INSPECTORS.get(classification.media_category, []):
        if (
            classification.extension
            and classification.extension in inspector.supported_extensions
        ):
            return inspector
        if (
            classification.mime_type
            and classification.mime_type in inspector.supported_mime_types
        ):
            return inspector
    return None