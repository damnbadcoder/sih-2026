import logging
from typing import Any

from lxml import etree

from app.core.formats import MEDIA_CATEGORY_IMAGE
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.processing.inspection.markup import _HARDENED_XML_PARSER
from app.storage import Storage

logger = logging.getLogger(__name__)

_SVG_MIME_TYPE = "image/svg+xml"
_MAX_SVG_TEXT_CHARS = 10 * 1024 * 1024
_TEXT_ELEMENTS = frozenset({"text", "tspan", "title", "desc"})
_SCRIPT_ELEMENTS = frozenset({"script"})
_REFERENCE_ATTRIBUTES = {"href", "src"}


class _SVGError(ValueError):
    """Internal signal for malformed SVG content."""


def _local_name(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


class SVGInspector(BaseInspector):
    """SVG inspector: deterministic structural text via a hardened XML parser.

    SVG is treated strictly as untrusted markup data — never rendered, never
    executed. Embedded scripts, external resources and network references are
    never loaded or fetched; they are only counted and reported as metadata.
    Element text from the text-bearing elements (``text``/``tspan``/``title``/
    ``desc``) is extracted and bounded. Files that do not parse as XML, or do
    not root in an ``<svg>`` element, become a controlled
    :class:`InspectionError`. No pixel/visual content is ever inferred.
    """

    media_category = MEDIA_CATEGORY_IMAGE
    supported_extensions = frozenset({".svg"})
    supported_mime_types = frozenset({_SVG_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                return _inspect(buffer)
            except _SVGError as exc:
                raise InspectionError("SVG file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _inspect(buffer) -> tuple[str | None, dict[str, Any]]:
    try:
        root = etree.parse(buffer, _HARDENED_XML_PARSER).getroot()
    except (etree.XMLSyntaxError, etree.LxmlError, ValueError, TypeError) as exc:
        raise _SVGError("SVG is malformed or unreadable") from exc

    if _local_name(root.tag) != "svg":
        raise _SVGError("SVG root element missing")

    pieces: list[str] = []
    total = 0
    truncated = False
    script_count = 0
    external_reference_count = 0
    for element in root.iter():
        name = _local_name(element.tag)
        if name in _SCRIPT_ELEMENTS:
            script_count += 1
        for attribute, value in element.attrib.items():
            if value and _local_name(attribute) in _REFERENCE_ATTRIBUTES and value.startswith(
                ("http://", "https://", "//")
            ):
                external_reference_count += 1
        if name in _TEXT_ELEMENTS and (element.text or "").strip():
            stripped = " ".join(element.text.split())
            pieces.append(stripped)
            total += len(stripped)
            if total >= _MAX_SVG_TEXT_CHARS:
                truncated = True

    metadata: dict[str, Any] = {
        "format": "svg",
        "text_char_count": total,
        "truncated": truncated,
        "script_count": script_count,
        "external_reference_count": external_reference_count,
    }
    for attribute in ("width", "height", "viewBox"):
        value = root.get(attribute)
        if value:
            metadata[attribute if attribute != "viewBox" else "view_box"] = value

    text = "\n".join(pieces)
    return (text if text else None), metadata