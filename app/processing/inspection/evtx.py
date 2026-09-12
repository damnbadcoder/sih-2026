import contextlib
import logging
import os
import tempfile
from typing import Any

from Evtx.Evtx import Evtx as _EvtxFile
from lxml import etree

from app.core.formats import MEDIA_CATEGORY_TEXT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.processing.inspection.markup import _HARDENED_XML_PARSER
from app.storage import Storage

logger = logging.getLogger(__name__)

_MAX_EVTX_RECORDS = 2000
_MAX_EVTX_TEXT_CHARS = 25 * 1024 * 1024
_EVENTS_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


class _EVTXError(ValueError):
    """Internal signal for structurally unreadable EVTX content."""


def _render_record(record) -> str | None:
    """Render one event record to its XML text, tolerating bad records."""
    try:
        element = record.lxml()
        if element is not None:
            return etree.tostring(element, encoding="unicode")
    except Exception:
        pass
    try:
        return record.xml()
    except Exception:
        return None


def _record_fields(element: etree._Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    system = element.find(f"{_EVENTS_NS}System")
    if system is not None:
        provider = system.find(f"{_EVENTS_NS}Provider")
        if provider is not None and provider.get("Name"):
            fields["provider"] = provider.get("Name")
        for tag in ("EventID", "Channel", "Computer"):
            node = system.find(f"{_EVENTS_NS}{tag}")
            value = node.text.strip() if node is not None and node.text else ""
            if value:
                fields[tag.lower()] = value
        created = system.find(f"{_EVENTS_NS}TimeCreated")
        if created is not None and created.get("SystemTime"):
            fields["time"] = created.get("SystemTime")
    data = element.find(f"{_EVENTS_NS}EventData")
    if data is not None:
        values = [
            (d.text or "").strip()
            for d in data.iter(f"{_EVENTS_NS}Data")
            if (d.text or "").strip()
        ]
        if values:
            fields["data"] = "\t".join(values)
    return fields


def _extract_event_line(xml: str, record_num: int) -> str:
    """Deterministic single-line rendering of an event record."""
    try:
        element = etree.fromstring(xml.encode("utf-8"), _HARDENED_XML_PARSER)
    except (etree.XMLSyntaxError, etree.LxmlError, ValueError):
        return ""
    fields = _record_fields(element)
    if not fields:
        return ""
    return (
        f"[{record_num}] "
        + " ".join(f"{key}={value}" for key, value in fields.items())
    )


class EVTXInspector(BaseInspector):
    """Windows Event Log (``.evtx``) inspector via ``python-evtx``.

    The log is parsed purely as data on Linux/Docker — no Windows APIs, no
    message-string resolution, no execution of anything in the log. Each
    record is rendered to XML and flattened into deterministic ``key=value``
    lines; individual malformed records are skipped and counted, while a
    structurally unreadable log becomes a controlled :class:`InspectionError`.
    Record and character counts are bounded.
    """

    media_category = MEDIA_CATEGORY_TEXT
    supported_extensions = frozenset({".evtx"})
    supported_mime_types = frozenset()

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        spool_path: str | None = None
        try:
            try:
                spool_path = _spool_to_disk(buffer)
                return _inspect(spool_path)
            except _EVTXError as exc:
                raise InspectionError("EVTX file is malformed or unreadable") from exc
        finally:
            buffer.close()
            if spool_path:
                with contextlib.suppress(OSError):
                    os.unlink(spool_path)


def _spool_to_disk(buffer) -> str:
    """Copy the validated buffer to a temp file (python-evtx mmaps a path)."""
    fd, path = tempfile.mkstemp(prefix="evtx_", suffix=".evtx")
    with os.fdopen(fd, "wb") as spool:
        while True:
            chunk = buffer.read(1024 * 1024)
            if not chunk:
                break
            spool.write(chunk)
    return path


def _inspect(path: str) -> tuple[str | None, dict[str, Any]]:
    with open(path, "rb") as probe:
        if probe.read(8) != b"ElfFile\x00":
            raise _EVTXError("EVTX file signature missing")
    pieces: list[str] = []
    total = 0
    records_processed = 0
    records_skipped = 0
    truncated_chars = False
    truncated_records = False
    try:
        with _EvtxFile(path) as log:
            for record in log.records():
                if records_processed >= _MAX_EVTX_RECORDS:
                    truncated_records = True
                    break
                xml = _render_record(record)
                if xml is None:
                    records_skipped += 1
                    continue
                records_processed += 1
                line = _extract_event_line(xml, records_processed)
                if not line:
                    continue
                pieces.append(line)
                total += len(line)
                if total >= _MAX_EVTX_TEXT_CHARS:
                    truncated_chars = True
                    break
    except Exception as exc:
        raise _EVTXError("EVTX log could not be read") from exc

    text = "\n".join(pieces)
    return (text if text else None), {
        "format": "evtx",
        "records_processed": records_processed,
        "records_skipped": records_skipped,
        "char_count": total,
        "truncated": truncated_chars or truncated_records,
    }