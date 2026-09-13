from app.processing.inspection.audio import AudioInspector
from app.processing.inspection.base import (
    BaseInspector,
    ContentInspector,
    InspectionError,
    InspectionResult,
    stream_to_buffer,
)
from app.processing.inspection.docx import DOCXInspector
from app.processing.inspection.pdf import PDFInspector
from app.processing.inspection.pptx import PPTXInspector
from app.processing.inspection.registry import get_inspector, register_inspector
from app.processing.inspection.text import TextInspector

__all__ = [
    "AudioInspector",
    "BaseInspector",
    "ContentInspector",
    "DOCXInspector",
    "InspectionError",
    "InspectionResult",
    "PDFInspector",
    "PPTXInspector",
    "TextInspector",
    "get_inspector",
    "register_inspector",
    "stream_to_buffer",
]