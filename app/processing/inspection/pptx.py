import logging

from pptx import Presentation

from app.core.formats import MEDIA_CATEGORY_PRESENTATION
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.storage import Storage

logger = logging.getLogger(__name__)

_PPTX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_MAX_PPTX_TEXT_CHARS = 25 * 1024 * 1024


def _slide_text_lines(slide) -> list[str]:
    """Collect deterministic text from a slide's shapes.

    Text frames and tables are traversed; grouped shapes are descended into.
    No notes, comments, embedded objects, macros or scripts are ever touched.
    """

    def walk(shapes, lines: list[str]) -> None:
        for shape in shapes:
            if shape.shape_type == 6:  # group
                walk(shape.shapes, lines)
                continue
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in paragraph.runs)
                    if line.strip():
                        lines.append(line)
            if shape.has_table:
                for row in shape.table.rows:
                    line = "\t".join(cell.text for cell in row.cells)
                    if line.strip():
                        lines.append(line)

    lines: list[str] = []
    walk(slide.shapes, lines)
    return lines


class PPTXInspector(BaseInspector):
    """PPTX presentation inspector: slide count plus slide-text extraction.

    ``python-pptx`` only parses the OOXML package as data; no macros, scripts
    or embedded executable content is run. Files that cannot be opened as a
    valid PPTX package become a controlled :class:`InspectionError`.
    """

    media_category = MEDIA_CATEGORY_PRESENTATION
    supported_extensions = frozenset({".pptx"})
    supported_mime_types = frozenset({_PPTX_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                presentation = Presentation(buffer)
                slide_count = len(presentation.slides)
                lines: list[str] = []
                total = 0
                truncated = False
                for slide in presentation.slides:
                    for line in _slide_text_lines(slide):
                        lines.append(line)
                        total += len(line)
                        if total >= _MAX_PPTX_TEXT_CHARS:
                            truncated = True
                            break
                    if truncated:
                        break
            except Exception as exc:
                raise InspectionError("PPTX file is malformed or unreadable") from exc
        finally:
            buffer.close()

        text = "\n".join(lines).strip()
        return (text or None), {
            "slide_count": slide_count,
            "char_count": total,
            "truncated": truncated,
        }