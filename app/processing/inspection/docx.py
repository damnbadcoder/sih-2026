import logging

from docx import Document

from app.core.formats import MEDIA_CATEGORY_DOCUMENT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.storage import Storage

logger = logging.getLogger(__name__)

_DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class DOCXInspector(BaseInspector):
    """DOCX inspector: paragraph count plus body-text extraction.

    ``python-docx`` only parses the OOXML package as data; no macros, scripts,
    or embedded executable content is run. Files that cannot be opened as a
    valid DOCX package become a controlled :class:`InspectionError`.
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".docx"})
    supported_mime_types = frozenset({_DOCX_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                document = Document(buffer)
                paragraphs = [paragraph.text for paragraph in document.paragraphs]
            except Exception as exc:
                raise InspectionError("DOCX file is malformed or unreadable") from exc
        finally:
            buffer.close()

        text = "\n".join(paragraphs).strip()
        return (text or None), {
            "paragraph_count": len(paragraphs),
            "char_count": len(text),
        }