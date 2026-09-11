import struct

from app.core.formats import MEDIA_CATEGORY_IMAGE
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SOI_MARKER = b"\xff\xd8"
_SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
_COLOR_TYPE_NAMES = {
    0: "grayscale",
    2: "truecolor",
    3: "indexed",
    4: "grayscale+alpha",
    6: "truecolor+alpha",
}


class ImageInspector(BaseInspector):
    """PNG/JPEG inspector: validates file magic and extracts image dimensions.

    Reads only the file header — no pixel data, no third-party libraries.
    If the declared extension contradicts the file's magic bytes the image is
    rejected as malformed (a mismatched upload that may be weaponized).
    OCR text extraction is intentionally left to the image grounding pipeline;
    this inspector produces only structural metadata.
    """

    media_category = MEDIA_CATEGORY_IMAGE
    supported_extensions = frozenset({".png", ".jpg", ".jpeg"})
    supported_mime_types = frozenset({"image/png", "image/jpeg"})

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                header = buffer.read(256 * 1024)
                return _inspect(header, file.original_filename)
            except (struct.error, ValueError, IndexError) as exc:
                raise InspectionError(
                    "image file is malformed or unreadable"
                ) from exc
        finally:
            buffer.close()


def _inspect(header: bytes, original_filename: str) -> tuple[None, dict]:
    if not header:
        raise ValueError("empty image file")
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext in ("jpg", "jpeg"):
        return _parse_jpeg(header)
    if ext == "png":
        return _parse_png(header)
    # Unknown extension — try to detect from magic but fail if ambiguous.
    if header.startswith(_PNG_SIGNATURE):
        return _parse_png(header)
    if header[:2] == _SOI_MARKER:
        return _parse_jpeg(header)
    raise ValueError("unrecognised image format")


def _parse_png(header: bytes) -> tuple[None, dict]:
    if not header.startswith(_PNG_SIGNATURE):
        raise ValueError("PNG signature missing")
    if len(header) < 33:
        raise ValueError("PNG header truncated before IHDR")
    # 8-byte signature, then 4-byte length (13 for IHDR), 4-byte type, then data.
    chunk_type = header[12:16]
    if chunk_type != b"IHDR":
        raise ValueError("PNG header is missing IHDR")
    width, height = struct.unpack(">II", header[16:24])
    bit_depth = header[24]
    color_type = header[25]
    if width == 0 or height == 0:
        raise ValueError("PNG dimensions are zero")
    return None, {
        "format": "png",
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": _COLOR_TYPE_NAMES.get(color_type, f"unknown({color_type})"),
    }


def _parse_jpeg(header: bytes) -> tuple[None, dict]:
    if len(header) < 4 or header[:2] != _SOI_MARKER:
        raise ValueError("JPEG SOI marker missing")
    pos = 2
    while pos + 2 <= len(header):
        if header[pos] != 0xFF:
            raise ValueError("JPEG marker boundary not aligned to 0xFF")
        marker = header[pos + 1]
        if marker == 0xD9:  # EOI
            break
        if marker == 0xDA:  # SOS — scan data begins, stop parsing
            break
        if marker == 0x00:
            pos += 1
            continue
        if (0xD0 <= marker <= 0xD7) or marker in (0xD8, 0x01):
            pos += 2
            continue
        if pos + 4 > len(header):
            raise ValueError("JPEG marker length extends beyond header window")
        length = struct.unpack(">H", header[pos + 2:pos + 4])[0]
        if marker in _SOF_MARKERS:
            precision = header[pos + 4]
            height = struct.unpack(">H", header[pos + 5:pos + 7])[0]
            width = struct.unpack(">H", header[pos + 7:pos + 9])[0]
            components = header[pos + 9]
            return None, {
                "format": "jpeg",
                "width": width,
                "height": height,
                "bit_depth": precision,
                "components": components,
            }
        pos += 2 + length
    raise ValueError("JPEG SOF marker not found in header")