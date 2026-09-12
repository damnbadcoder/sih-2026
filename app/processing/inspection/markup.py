import json
import logging
from pathlib import PurePosixPath
from typing import Any

from lxml import etree

from app.core.formats import MEDIA_CATEGORY_TEXT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.processing.inspection.text import _decode_text, flatten_json
from app.storage import Storage

logger = logging.getLogger(__name__)

_MAX_XML_TEXT_CHARS = 10 * 1024 * 1024

# Hardened XML parser: external entities, DTD subsets and network access are
# all disabled, so untrusted XML/RSS/Atom/SVG/STIX files can never trigger
# XXE, external entity resolution or entity-expansion (billion laughs) bombs.
# ``huge_tree`` stays off (lxml's built-in tree-size/depth limits apply).
_HARDENED_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
)


class _MarkupError(ValueError):
    """Internal signal for malformed markup content."""


class MarkupInspector(BaseInspector):
    """XML-family inspector: ``.xml``, ``.rss``, ``.atom`` and, for STIX/TAXII
    bundles, either XML or JSON payloads.

    Element text is extracted deterministically with a hardened lxml parser
    (no entity resolution, no DTD loading, no network). STIX/TAXII content is
    sniffed rather than trusted: XML syntax goes through the hardened parser,
    JSON syntax is flattened via the shared JSON renderer. Content is treated
    strictly as data — never rendered, fetched or executed.
    """

    media_category = MEDIA_CATEGORY_TEXT
    supported_extensions = frozenset({".xml", ".rss", ".atom", ".stix", ".taxii"})
    supported_mime_types = frozenset(
        {
            "application/xml",
            "text/xml",
            "application/rss+xml",
            "application/atom+xml",
            "application/json",
        }
    )

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                return _inspect(buffer, file.original_filename)
            except _MarkupError as exc:
                raise InspectionError(
                    "structured markup file is malformed or unreadable"
                ) from exc
        finally:
            buffer.close()


def _inspect(buffer, original_filename: str) -> tuple[str | None, dict[str, Any]]:
    extension = PurePosixPath(original_filename).suffix.lower()
    probe = buffer.read(1024)
    stripped = probe.lstrip()
    if not stripped:
        raise _MarkupError("empty markup file")
    if stripped[:1] in (b"{", b"["):
        buffer.seek(0)
        return _extract_json(buffer.read(), extension)
    buffer.seek(0)
    return _extract_xml(buffer, extension)


def _extract_xml(buffer, extension: str) -> tuple[str | None, dict[str, Any]]:
    try:
        root = etree.parse(buffer, _HARDENED_XML_PARSER).getroot()
    except (etree.XMLSyntaxError, etree.LxmlError, ValueError) as exc:
        raise _MarkupError("XML is malformed or unreadable") from exc

    pieces: list[str] = []
    total = 0
    truncated = False
    for text in root.itertext():
        stripped = " ".join(text.split())
        if not stripped:
            continue
        pieces.append(stripped)
        total += len(stripped)
        if total >= _MAX_XML_TEXT_CHARS:
            truncated = True
            break

    tag = root.tag
    local_name = tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
    rendered = "\n".join(pieces)
    return (rendered or None), {
        "format": extension[1:] if extension else "xml",
        "root": local_name,
        "char_count": total,
        "truncated": truncated,
    }


def _extract_json(data: bytes, extension: str) -> tuple[str | None, dict[str, Any]]:
    text = _decode_text(data)
    try:
        value = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise _MarkupError("JSON content is malformed or unreadable") from exc
    rendered = "\n".join(flatten_json(value))
    return (rendered or None), {
        "format": extension[1:] if extension else "json",
        "encoding": "json",
        "char_count": len(rendered),
        "truncated": False,
    }