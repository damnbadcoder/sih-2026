import struct

from app.core.formats import MEDIA_CATEGORY_VIDEO
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer


class BoxStructureError(ValueError):
    pass


class _BoxReader:
    """Minimal ISO-BMFF (MP4) box reader over a seekable buffer.

    Container boxes (``moov``/``trak``/``mdia``/``minf``) are descended into;
    media boxes (``mdat``...) are skipped with an absolute seek, so memory
    stays bounded for arbitrary sources.
    """

    def __init__(self, buffer):
        self._file = buffer

    def _take(self, n: int) -> bytes:
        chunk = self._file.read(n)
        if len(chunk) != n:
            raise BoxStructureError("box truncated")
        return chunk

    def box(self) -> tuple[int, bytes, int] | None:
        """Return ``(size, type, header_length)`` of the next box.

        The file cursor is left just after the box header. Returns ``None``
        at a clean EOF.
        """
        header = self._file.read(8)
        if not header:
            return None
        if len(header) < 8:
            raise BoxStructureError("box header truncated")
        size = struct.unpack(">I", header[:4])[0]
        box_type = header[4:8]
        header_len = 8
        if size == 1:
            size = struct.unpack(">Q", self._take(8))[0]
            header_len = 16
        elif size == 0:
            current = self._file.tell()
            self._file.seek(0, 2)
            size = self._file.tell() - current + 8
            self._file.seek(current)
        if size < header_len or box_type == b"\x00\x00\x00\x00":
            raise BoxStructureError("box size too small or type empty")
        return size, box_type, header_len


class VideoInspector(BaseInspector):
    """MP4 inspector: parses the ISO-BMFF container for metadata.

    Standard-library only. Extracts the Ftyp brand, the ``mvhd`` duration,
    the first non-zero ``tkhd`` track dimensions and the media handler types
    (``vide``/``soun``). Video transcription is intentionally left to the
    video grounding pipeline; this inspector performs no decoding.
    """

    media_category = MEDIA_CATEGORY_VIDEO
    supported_extensions = frozenset({".mp4"})
    supported_mime_types = frozenset({"video/mp4"})

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            return _inspect(buffer)
        except (struct.error, BoxStructureError) as exc:
            raise InspectionError("video file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _inspect(buffer) -> tuple[None, dict]:
    reader = _BoxReader(buffer)
    info: dict = {"brand": None, "duration": None, "handlers": set(), "width": None, "height": None}

    first = reader.box()
    if first is None or first[1] != b"ftyp":
        raise BoxStructureError("FTYP box missing")
    size, _box_type, header_len = first
    info["brand"] = _major_brand(reader)
    reader._file.seek(size - header_len - 4, 1)  # brand already consumed 4 payload bytes

    while True:
        box = reader.box()
        if box is None:
            break
        size, box_type, header_len = box
        if box_type == b"moov":
            _parse_container(reader, size, header_len, info)
        elif box_type == b"ftyp":
            reader._file.seek(size - header_len, 1)  # tolerate a stray second ftyp
        else:
            reader._file.seek(size - header_len, 1)

    if info["brand"] is None:
        raise BoxStructureError("FTYP brand missing")

    duration = info["duration"]
    return None, {
        "format": "mp4",
        "brand": info["brand"],
        "duration_seconds": round(duration, 2) if duration is not None else None,
        "has_video": "vide" in info["handlers"],
        "has_audio": "soun" in info["handlers"],
        "width": info["width"],
        "height": info["height"],
    }


def _major_brand(reader: _BoxReader) -> str:
    raw = reader._take(4)
    return raw.decode("ascii", errors="replace") or "mp4"


_CONTAINER_TYPES = {
    b"moov",
    b"trak",
    b"mdia",
    b"minf",
    b"stbl",
}


def _parse_container(reader: _BoxReader, size: int, header_len: int, info: dict) -> None:
    end = reader._file.tell() + (size - header_len)
    while reader._file.tell() < end:
        box = reader.box()
        if box is None:
            return
        child_size, child_type, child_header_len = box
        payload_end = reader._file.tell() + (child_size - child_header_len)
        if child_type == b"mvhd":
            duration = _parse_mvhd(reader)
            if duration is not None:
                info["duration"] = duration
        elif child_type == b"tkhd":
            width, height = _parse_tkhd(reader)
            if width and height and info["width"] is None:
                info["width"], info["height"] = width, height
        elif child_type == b"hdlr":
            handler = _parse_hdlr(reader)
            if handler:
                info["handlers"].add(handler)
        elif child_type in _CONTAINER_TYPES:
            _parse_container(reader, child_size, child_header_len, info)
            payload_end = None  # recursion already aligned the cursor
        reader._file.seek(payload_end, 0) if payload_end is not None else None
    reader._file.seek(end, 0)


def _parse_mvhd(reader: _BoxReader) -> float | None:
    version = reader._take(1)[0]
    reader._take(3)  # flags
    if version == 1:
        reader._take(16)  # creation/modification (u64 x2)
        timescale = struct.unpack(">I", reader._take(4))[0]
        duration = struct.unpack(">Q", reader._take(8))[0]
    else:
        reader._take(8)  # creation/modification (u32 x2)
        timescale = struct.unpack(">I", reader._take(4))[0]
        duration = struct.unpack(">I", reader._take(4))[0]
    if not timescale:
        return None
    return duration / timescale


def _parse_tkhd(reader: _BoxReader) -> tuple[int | None, int | None]:
    version = reader._take(1)[0]
    reader._take(3)  # flags
    width_offset = 84 if version == 1 else 72
    reader._take(width_offset)
    width = struct.unpack(">I", reader._take(4))[0] // 65536
    height = struct.unpack(">I", reader._take(4))[0] // 65536
    return width or None, height or None


def _parse_hdlr(reader: _BoxReader) -> str | None:
    reader._take(4)  # version + flags
    reader._take(4)  # pre_defined
    handler_type = reader._take(4)
    decoded = handler_type.decode("ascii", errors="replace").lower()
    return decoded if decoded.isalpha() else None