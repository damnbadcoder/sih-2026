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
_BMP_COMPRESSION_NAMES = {
    0: "none",
    1: "RLE8",
    2: "RLE4",
    3: "bitfields",
    4: "JPEG",
    5: "PNG",
    6: "alpha-bitfields",
}
_TIFF_COMPRESSION_NAMES = {
    1: "none",
    2: "CCITT RLE",
    3: "CCITT Group 3",
    4: "CCITT Group 4",
    5: "LZW",
    6: "old-style JPEG",
    7: "JPEG",
    8: "Deflate",
    32773: "PackBits",
    32946: "Deflate",
}
_TIFF_PHOTOMETRIC_NAMES = {
    0: "white-is-zero",
    1: "black-is-zero",
    2: "RGB",
    3: "palette",
    4: "transparency-mask",
    5: "CMYK",
    6: "YCbCr",
    8: "CIELab",
}
_TIFF_SAMPLE_TAGS = frozenset({256, 257, 258, 259, 262})  # width/height/bps/compression/photometric


class ImageInspector(BaseInspector):
    """PNG/JPEG inspector: validates file magic and extracts image dimensions.

    Reads only the file header — no pixel data, no third-party libraries.
    If the declared extension contradicts the file's magic bytes the image is
    rejected as malformed (a mismatched upload that may be weaponized).
    OCR text extraction is intentionally left to the image grounding pipeline;
    this inspector produces only structural metadata.
    """

    media_category = MEDIA_CATEGORY_IMAGE
    supported_extensions = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"})
    supported_mime_types = frozenset(
        {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/x-ms-bmp", "image/tiff"}
    )

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
    if ext == "bmp":
        return _parse_bmp(header)
    if ext == "webp":
        return _parse_webp(header)
    if ext in ("tiff", "tif"):
        return _parse_tiff(header)
    # Unknown extension — try to detect from magic but fail if ambiguous.
    if header.startswith(_PNG_SIGNATURE):
        return _parse_png(header)
    if header[:2] == _SOI_MARKER:
        return _parse_jpeg(header)
    if header[:2] == b"BM":
        return _parse_bmp(header)
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return _parse_webp(header)
    if header[:2] in (b"II", b"MM") and len(header) >= 8:
        order = "<" if header[:2] == b"II" else ">"
        if struct.unpack(f"{order}H", header[2:4])[0] == 42:
            return _parse_tiff(header)
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


def _parse_bmp(header: bytes) -> tuple[None, dict]:
    if len(header) < 26 or not header.startswith(b"BM"):
        raise ValueError("BMP signature missing")
    header_size = struct.unpack("<I", header[14:18])[0]
    if header_size == 12:  # BITMAPCOREHEADER (OS/2 2.x)
        width = struct.unpack("<H", header[18:20])[0]
        height = struct.unpack("<H", header[20:22])[0]
        bit_depth = struct.unpack("<H", header[24:26])[0]
        compression = 0
    elif header_size >= 40:  # BITMAPINFOHEADER / BITMAPV4HEADER / +
        width = struct.unpack("<i", header[18:22])[0]
        height = struct.unpack("<i", header[22:26])[0]
        bit_depth = struct.unpack("<H", header[28:30])[0]
        compression = struct.unpack("<I", header[30:34])[0]
    else:
        raise ValueError("BMP header size unsupported")
    if width <= 0 or height == 0:
        raise ValueError("BMP dimensions are zero or negative")
    if height < 0:  # negative height = top-down row order, same dimensions
        height = -height
    return None, {
        "format": "bmp",
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "compression": _BMP_COMPRESSION_NAMES.get(compression, f"unknown({compression})"),
    }


def _parse_webp(header: bytes) -> tuple[None, dict]:
    if len(header) < 20 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        raise ValueError("WebP RIFF signature missing")
    pos = 12
    width = height = None
    variant = None
    while pos + 8 <= len(header):
        chunk_type = header[pos:pos + 4]
        chunk_size = struct.unpack("<I", header[pos + 4:pos + 8])[0]
        data_start = pos + 8
        data = header[data_start:data_start + chunk_size]
        if len(data) < chunk_size:
            break  # chunk extends beyond the header window
        if chunk_type == b"VP8 " and len(data) >= 10 and data[3:6] == b"\x9d\x01\x2a":
            width = ((data[6] | ((data[7] & 0x3F) << 8)) & 0x3FFF) + 1
            height = ((data[8] | ((data[9] & 0x3F) << 8)) & 0x3FFF) + 1
            variant = "lossy"
        elif chunk_type == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
            bits = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24)
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            variant = "lossless"
        elif chunk_type == b"VP8X" and len(data) >= 10:
            width = int.from_bytes(data[4:7], "little") + 1
            height = int.from_bytes(data[7:10], "little") + 1
            variant = "extended"
        if width and height:
            break
        pos = data_start + chunk_size + (chunk_size & 1)  # chunks are padded to even sizes
    if not width or not height:
        raise ValueError("WebP dimensions not found in header")
    return None, {
        "format": "webp",
        "width": width,
        "height": height,
        "variant": variant,
    }


def _parse_tiff(header: bytes) -> tuple[None, dict]:
    if len(header) < 8 or header[:2] not in (b"II", b"MM"):
        raise ValueError("TIFF endian marker missing")
    order = "<" if header[:2] == b"II" else ">"
    if struct.unpack(f"{order}H", header[2:4])[0] != 42:
        raise ValueError("TIFF magic 42 missing")
    ifd_offset = struct.unpack(f"{order}I", header[4:8])[0]
    if ifd_offset + 2 > len(header):
        raise ValueError("TIFF IFD falls outside the header window")
    entry_count = struct.unpack(f"{order}H", header[ifd_offset:ifd_offset + 2])[0]
    tags: dict[int, int] = {}
    pos = ifd_offset + 2
    for _ in range(entry_count):
        if pos + 12 > len(header):
            raise ValueError("TIFF IFD truncated")
        tag = struct.unpack(f"{order}H", header[pos:pos + 2])[0]
        field_type = struct.unpack(f"{order}H", header[pos + 2:pos + 4])[0]
        count = struct.unpack(f"{order}I", header[pos + 4:pos + 8])[0]
        if tag in _TIFF_SAMPLE_TAGS and count == 1:
            if field_type in (4, 13):  # LONG / IFD stored inline
                tags[tag] = struct.unpack(f"{order}I", header[pos + 8:pos + 12])[0]
            elif field_type == 3:  # SHORT (two low bytes of the value field)
                tags[tag] = struct.unpack(f"{order}H", header[pos + 8:pos + 10])[0]
        pos += 12

    width = tags.get(256)
    height = tags.get(257)
    if not width or not height:
        raise ValueError("TIFF missing image dimensions")
    metadata: dict = {
        "format": "tiff",
        "width": width,
        "height": height,
    }
    if bit_depth := tags.get(258):
        metadata["bit_depth"] = bit_depth
    if compression := tags.get(259):
        metadata["compression"] = _TIFF_COMPRESSION_NAMES.get(
            compression, f"unknown({compression})"
        )
    if photometric := tags.get(262):
        metadata["photometric"] = _TIFF_PHOTOMETRIC_NAMES.get(
            photometric, f"unknown({photometric})"
        )
    return None, metadata