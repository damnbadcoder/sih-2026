import logging
from typing import Any

import xlrd
from xlrd import xldate_as_datetime

from app.core.formats import MEDIA_CATEGORY_DOCUMENT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.storage import Storage

logger = logging.getLogger(__name__)

_XLS_MIME_TYPE = "application/vnd.ms-excel"
_MAX_XLS_ROWS = 100_000
_MAX_XLS_TEXT_CHARS = 25 * 1024 * 1024


def _cell_text(cell: Any, datemode: int) -> str:
    """Render a single XLS cell deterministically.

    Formulas are never evaluated: xlrd only exposes the stored cached value
    (or an empty cell for formula cells with no cache), so no macro/formula
    code can ever run during inspection.
    """
    if cell.ctype == xlrd.XL_CELL_TEXT:
        return str(cell.value)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        value = float(cell.value)
        return str(int(value)) if value == int(value) else str(value)
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xldate_as_datetime(cell.value, datemode).isoformat(sep=" ")
        except (ValueError, OverflowError):
            return ""
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if cell.value else "FALSE"
    return ""


class XLSInspector(BaseInspector):
    """XLS spreadsheet inspector: cell text extraction via ``xlrd``.

    The legacy binary XLS format needs a real parser; `xlrd` provides one
    without any formula or macro execution (only cached cell values are ever
    read). The workbook is loaded as data from a bounded buffer and rows/cells
    are further bounded during extraction. Files that cannot be parsed as a
    valid BIFF workbook become a controlled :class:`InspectionError`.
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".xls"})
    supported_mime_types = frozenset({_XLS_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                data = buffer.read()
                workbook = xlrd.open_workbook(file_contents=data)
                return _extract_workbook(workbook)
            except (xlrd.XLRDError, ValueError, IndexError, MemoryError, OverflowError) as exc:
                raise InspectionError("XLS file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _extract_workbook(workbook: xlrd.Book) -> tuple[str | None, dict[str, Any]]:
    pieces: list[str] = []
    total = 0
    truncated = False
    row_count = 0
    cell_count = 0
    for sheet in workbook.sheets():
        for row_index in range(min(sheet.nrows, _MAX_XLS_ROWS)):
            values = [
                value
                for col_index in range(sheet.ncols)
                if (value := _cell_text(sheet.cell(row_index, col_index), workbook.datemode))
            ]
            cell_count += sheet.ncols
            if values:
                pieces.append("\t".join(values))
                total += len(pieces[-1])
                if total >= _MAX_XLS_TEXT_CHARS:
                    truncated = True
                    break
            row_count += 1
        if truncated:
            break

    text = "\n".join(pieces)
    return (text if text else None), {
        "format": "xls",
        "sheet_count": workbook.nsheets,
        "row_count": row_count,
        "cell_count": cell_count,
        "char_count": total,
        "truncated": truncated,
    }