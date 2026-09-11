import re
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.formats import MEDIA_CATEGORY_DOCUMENT
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer

_XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_SHEET_RE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
_SHEET_NAME_RE = re.compile(r"^xl/worksheets/sheet(\d+)\.xml$")
_CELL_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _sheet_order(name: str) -> int:
    match = _SHEET_NAME_RE.match(name)
    return int(match.group(1)) if match else 0


def _cell_text(shared_strings: list[str], cell: ET.Element) -> str:
    cell_type = cell.get("t")
    if cell_type == "s":
        raw = cell.findtext(f"{_CELL_NS}v") or ""
        try:
            index = int(raw.strip())
        except ValueError:
            return ""
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return ""
    if cell_type == "inlineStr":
        return "".join(
            t.text or "" for t in cell.iterfind(f"{_CELL_NS}is/{_CELL_NS}t")
        )
    return (cell.findtext(f"{_CELL_NS}v") or "").strip()


class XLSXInspector(BaseInspector):
    """XLSX spreadsheet inspector: streaming cell text via the ZIP + XML layers.

    Implemented with only the standard library (``zipfile`` + ``xml.etree``),
    streaming sheets incrementally so memory stays bounded for arbitrary
    workbook sizes. Each non-empty row becomes a tab-separated line of its
    non-empty cell values (shared strings, inline strings and raw numbers).
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".xlsx"})
    supported_mime_types = frozenset({_XLSX_MIME_TYPE})

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                return _extract_workbook(buffer)
            except (BadZipFile, ET.ParseError, KeyError, ValueError, MemoryError) as exc:
                raise InspectionError(
                    "XLSX file is malformed or unreadable"
                ) from exc
        finally:
            buffer.close()


def _load_shared_strings(archive: ZipFile, char_cap: int) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings: list[str] = []
    total = 0
    with archive.open("xl/sharedStrings.xml") as stream:
        for _event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag == f"{_CELL_NS}si":
                value = "".join(t.text or "" for t in elem.iter(f"{_CELL_NS}t"))
                strings.append(value)
                total += len(value)
                elem.clear()
            if total >= char_cap:
                break
    return strings


def _extract_workbook(buffer) -> tuple[str | None, dict]:
    char_cap = 25 * 1024 * 1024
    with ZipFile(buffer) as archive:
        sheet_names = sorted(
            (name for name in archive.namelist() if _SHEET_RE.match(name)),
            key=_sheet_order,
        )
        if not sheet_names:
            raise InspectionError("XLSX file contains no worksheets")
        shared_strings = _load_shared_strings(archive, char_cap)

        pieces: list[str] = []
        total = 0
        truncated = False
        row_count = 0
        cell_count = 0
        for sheet in sheet_names:
            with archive.open(sheet) as stream:
                for _event, elem in ET.iterparse(stream, events=("end",)):
                    if elem.tag != f"{_CELL_NS}row":
                        continue
                    row_values: list[str] = []
                    for cell in elem.iter(f"{_CELL_NS}c"):
                        cell_count += 1
                        value = _cell_text(shared_strings, cell)
                        if value:
                            row_values.append(value)
                    if row_values:
                        pieces.append("\t".join(row_values))
                        total += len(pieces[-1])
                        if total >= char_cap:
                            truncated = True
                            break
                    row_count += 1
                    elem.clear()
            if truncated:
                break

    text = "\n".join(pieces)
    return (text if text else None), {
        "format": "xlsx",
        "sheet_count": len(sheet_names),
        "row_count": row_count,
        "cell_count": cell_count,
        "char_count": total,
        "truncated": truncated,
    }