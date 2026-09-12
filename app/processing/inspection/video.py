import struct

from app.core.formats import MEDIA_CATEGORY_VIDEO
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer


class BoxStructureError(ValueError):
    pass


class _BoxReader:
    """Minimal parser over a seekable buffer with bounded sequential reads.

    ``_take`` is the only primitive: it reads a fixed number of bytes and
    raises on truncation. MP4/MOV boxes, EBML (Matroska/WebM) elements and
    RIFF (AVI) chunks are all walked with absolute seeks, so memory stays
    bounded for arbitrary sources.
    """

    def __init__(self, buffer):
        self._file = buffer

    def _take(self, n: int) -> bytes:
        chunk = self._file.read(n)
        if len(chunk) != n:
            raise BoxStructureError("container truncated")
        return chunk

    def box(self) -> tuple[int, bytes, int] | None:
        """ISO-BMFF box header as ``(size, type, header_length)`` or None."""
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


# --- ISO-BMFF (MP4 / MOV) ----------------------------------------------------


class VideoInspector(BaseInspector):
    """Video inspector: MP4/MOV (ISO-BMFF), MKV/WebM (EBML) and AVI (RIFF).

    Standard-library only. Extracts container-level metadata (brand/doctype,
    duration, track dimensions, media handler or codec types). Video
    transcription is intentionally left to the video grounding pipeline; this
    inspector performs no decoding and never renders frames.
    """

    media_category = MEDIA_CATEGORY_VIDEO
    supported_extensions = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi"})
    supported_mime_types = frozenset(
        {
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
            "video/x-msvideo",
            "video/avi",
        }
    )

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                return _inspect(buffer, _extension(file.original_filename))
            except (struct.error, BoxStructureError, IndexError) as exc:
                raise InspectionError("video file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _inspect(buffer, ext: str) -> tuple[None, dict]:
    probe = buffer.read(12)
    buffer.seek(0)
    if not probe:
        raise BoxStructureError("empty video file")
    if probe[:4] == b"\x1a\x45\xdf\xa3":
        return _parse_ebml(buffer, ext)
    if probe[:4] == b"RIFF":
        return _parse_riff_avi(buffer)
    return _parse_mp4(buffer, ext)


def _parse_mp4(buffer, ext: str) -> tuple[None, dict]:
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
        "format": "mov" if ext == "mov" else "mp4",
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


# --- EBML (Matroska / WebM) --------------------------------------------------


_EBML_CONTAINERS = frozenset(
    {
        0x1A45DFA3,  # EBML
        0x18538067,  # Segment
        0x1549A966,  # Info
        0x1654AE6B,  # Tracks
        0xAE,  # TrackEntry
        0xE0,  # Video
        0xE1,  # Audio
        0x1F43B675,  # Cluster (skipped)
    }
)


def _ebml_id_length(reader: _BoxReader) -> int:
    first = reader._take(1)[0]
    mask = 0x80
    length = 1
    while not (first & mask):
        mask >>= 1
        length += 1
        if length > 8:
            raise BoxStructureError("EBML element ID too long")
    reader._file.seek(-1, 1)
    return length


def _ebml_size_value(reader: _BoxReader) -> int:
    first = reader._take(1)[0]
    mask = 0x80
    length = 1
    while not (first & mask):
        mask >>= 1
        length += 1
        if length > 8:
            raise BoxStructureError("EBML element size too long")
    value = first & (mask - 1)
    for _ in range(length - 1):
        value = (value << 8) | reader._take(1)[0]
    if value == (1 << (7 * length)) - 1:
        return -1  # unknown size (valid for Segment)
    return value


def _parse_ebml(buffer, ext: str) -> tuple[None, dict]:
    reader = _BoxReader(buffer)
    state: dict = {
        "doctype": None,
        "duration": None,
        "timecode_scale": 1000000,
        "codec_ids": set(),
        "track_types": set(),
        "width": None,
        "height": None,
        "sampling_rate": None,
        "channels": None,
    }

    if _read_ebml_id(reader) != 0x1A45DFA3:
        raise BoxStructureError("EBML header marker missing")
    header_size = _ebml_size_value(reader)
    header_end = reader._file.tell() + header_size
    _consume_ebml_children(reader, header_end, state)
    reader._file.seek(header_end)

    if _read_ebml_id(reader) != 0x18538067:
        raise BoxStructureError("Segment element missing")
    size = _ebml_size_value(reader)
    if size < 0:
        reader._file.seek(0, 2)
        segment_end = reader._file.tell()
    else:
        segment_end = reader._file.tell() + size
    _consume_ebml_children(reader, segment_end, state)

    duration = state["duration"]
    scale = state["timecode_scale"]
    return None, {
        "format": "webm" if ext == "webm" else "mkv",
        "doctype": state["doctype"],
        "duration_seconds": round(duration * scale / 1_000_000_000, 2)
        if duration is not None and scale
        else None,
        "codecs": ",".join(sorted(state["codec_ids"])) or None,
        "has_video": 1 in state["track_types"],
        "has_audio": 2 in state["track_types"],
        "width": state["width"],
        "height": state["height"],
        "sample_rate_hz": state["sampling_rate"],
        "channels": state["channels"],
    }


def _read_ebml_id(reader: _BoxReader) -> int:
    length = _ebml_id_length(reader)
    return int.from_bytes(reader._take(length), "big")


def _consume_ebml_children(reader: _BoxReader, end: int, state: dict, depth: int = 0) -> None:
    if depth > 16:
        raise BoxStructureError("EBML nesting too deep")
    budget = 0
    while reader._file.tell() < end and budget < 4096:
        budget += 1
        element_id = _read_ebml_id(reader)
        size = _ebml_size_value(reader)
        if size < 0:
            raise BoxStructureError("unknown element size outside Segment")
        if element_id in _EBML_CONTAINERS:
            child_end = reader._file.tell() + size
            if element_id == 0x1F43B675:  # Cluster: timing data only, skip wholesale
                reader._file.seek(child_end)
                continue
            _consume_ebml_children(reader, child_end, state, depth + 1)
            reader._file.seek(child_end)
        else:
            payload = reader._file.read(size)
            if len(payload) != size:
                raise BoxStructureError("EBML element truncated")
            _record_ebml_value(element_id, payload, state)


def _record_ebml_value(element_id: int, payload: bytes, state: dict) -> None:
    if element_id == 0x4282:
        state["doctype"] = payload.decode("utf-8", errors="replace")
        return
    if element_id == 0x2AD7B1:
        state["timecode_scale"] = int.from_bytes(payload, "big")
        return
    if element_id == 0x4489 and len(payload) == 8:
        state["duration"] = struct.unpack(">d", payload)[0]
        return
    if element_id == 0x83:
        state["track_types"].add(int.from_bytes(payload, "big"))
        return
    if element_id == 0x86:
        state["codec_ids"].add(payload.decode("utf-8", errors="replace"))
        return
    if element_id == 0xB0:
        state["width"] = int.from_bytes(payload, "big")
        return
    if element_id == 0xBA:
        state["height"] = int.from_bytes(payload, "big")
        return
    if element_id == 0xB5 and len(payload) == 8:
        state["sampling_rate"] = struct.unpack(">d", payload)[0]
        return
    if element_id == 0x9F:
        state["channels"] = int.from_bytes(payload, "big")


# --- RIFF (AVI) --------------------------------------------------------------


def _parse_riff_avi(buffer) -> tuple[None, dict]:
    reader = _BoxReader(buffer)
    header = reader._take(12)
    if header[:4] != b"RIFF" or header[8:12] != b"AVI ":
        raise BoxStructureError("AVI RIFF signature missing")
    end = reader._file.tell() + (struct.unpack("<I", header[4:8])[0] - 4)
    info: dict = {
        "width": None,
        "height": None,
        "bit_depth": None,
        "total_frames": None,
        "microsec_per_frame": None,
        "stream_count": 0,
        "video_streams": 0,
        "audio_streams": 0,
    }
    while reader._file.tell() < end:
        _walk_riff_chunk(reader, info)
    _finish_avi(info)
    return None, info | {"format": "avi"}


def _walk_riff_chunk(reader: _BoxReader, info: dict) -> None:
    chunk_id = reader._take(4)
    chunk_size = struct.unpack("<I", reader._take(4))[0]
    if chunk_id == b"LIST":
        list_type = reader._take(4)
        list_end = reader._file.tell() + chunk_size - 4
        if list_type in (b"hdrl", b"strl"):
            while reader._file.tell() < list_end:
                _walk_riff_chunk(reader, info)
        reader._file.seek(list_end)
        return
    payload_end = reader._file.tell() + chunk_size
    if chunk_id == b"avih":
        _parse_avih(reader, info)
    elif chunk_id == b"strh":
        _parse_strh(reader, info)
    elif chunk_id == b"strf":
        size = payload_end - reader._file.tell()
        _parse_strf(reader, info, size)
    reader._file.seek(payload_end + (chunk_size & 1))  # RIFF chunks pad to even sizes


def _parse_avih(reader: _BoxReader, info: dict) -> None:
    payload = reader._take(56)
    info["microsec_per_frame"] = struct.unpack("<I", payload[0:4])[0]
    info["total_frames"] = struct.unpack("<I", payload[16:20])[0]
    info["stream_count"] = struct.unpack("<I", payload[24:28])[0]
    if info["width"] is None:
        width = struct.unpack("<I", payload[32:36])[0]
        height = struct.unpack("<I", payload[36:40])[0]
        if width and height:
            info["width"], info["height"] = width, height


def _parse_strh(reader: _BoxReader, info: dict) -> None:
    payload = reader._take(56)
    stream_type = payload[0:4]
    scale = struct.unpack("<I", payload[20:24])[0]
    rate = struct.unpack("<I", payload[24:28])[0]
    if stream_type == b"vids":
        info["video_streams"] += 1
    elif stream_type == b"auds":
        info["audio_streams"] += 1
    if scale and rate and info.get("fps") is None:
        info["fps"] = round(rate / scale, 4)


def _parse_strf(reader: _BoxReader, info: dict, size: int) -> None:
    if size >= 40:
        payload = reader._take(40)
        header_size = struct.unpack("<I", payload[0:4])[0]
        if header_size >= 40:  # BITMAPINFOHEADER (video)
            width = struct.unpack("<i", payload[4:8])[0]
            height = struct.unpack("<i", payload[8:12])[0]
            bit_depth = struct.unpack("<H", payload[14:16])[0]
            if width > 0 and not info["width"]:
                info["width"], info["height"] = width, abs(height)
            if bit_depth and info["bit_depth"] is None:
                info["bit_depth"] = bit_depth
        return
    if size >= 16:  # WAVEFORMATEX (audio)
        payload = reader._take(16)
        if info.get("audio_channels") is None:
            info["audio_rate_hz"] = struct.unpack("<I", payload[4:8])[0]
            info["audio_channels"] = struct.unpack("<H", payload[2:4])[0]
            info["audio_bits"] = struct.unpack("<H", payload[14:16])[0]


def _finish_avi(info: dict) -> None:
    fps = info.get("fps")
    if fps is None and info["microsec_per_frame"]:
        fps = round(1_000_000 / info["microsec_per_frame"], 4)
    if fps is None:
        fps = 25.0  # AVI fallback
    total_frames = info["total_frames"]
    info["fps"] = fps
    info["duration_estimate_seconds"] = round(total_frames / fps, 2) if total_frames else None
    info["has_video"] = info["video_streams"] > 0
    info["has_audio"] = info["audio_streams"] > 0