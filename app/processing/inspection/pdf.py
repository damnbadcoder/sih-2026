import logging

from pypdf import PdfReader

from app.core.formats import MEDIA_CATEGORY_DOCUMENT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.storage import Storage

logger = logging.getLogger(__name__)


class PDFInspector(BaseInspector):
    """PDF inspector: page count plus best-effort per-page text extraction.

    ``pypdf`` is run purely to read and layout-recover text; nothing is
    executed, evaluated, or decompressed into a hostile context. A page whose
    extraction fails contributes no text, never aborts the job. Files that
    ``pypdf`` cannot parse at all become a controlled :class:`InspectionError`.
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".pdf"})
    supported_mime_types = frozenset({"application/pdf"})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                reader = PdfReader(buffer)
            except Exception as exc:
                raise InspectionError("PDF file is malformed or unreadable") from exc
            try:
                page_count = len(reader.pages)
            except Exception as exc:
                raise InspectionError("PDF file could not be parsed") from exc

            page_texts: list[str] = []
            for page in reader.pages:
                try:
                    text = (page.extract_text() or "").strip()
                except Exception:
                    text = ""
                page_texts.append(text)

            text = "\n\n".join(page_texts).strip()
            return (text or None), {"page_count": page_count, "char_count": len(text)}
        finally:
            buffer.close()