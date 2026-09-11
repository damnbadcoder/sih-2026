import struct

from app.core.formats import MEDIA_CATEGORY_AUDIO
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer

_AUDIO_HEADER_WINDOW = 1024 * 1024

# bitrate_index is 1..14 pointing into these tables (0 and 15 are reserved).
_BITRATES_MPEG1_L1 = [32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448]
_BITRATES_MPEG1_L2 = [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384]
_BITRATES_MPEG1_L3 = [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_BITRATES_MPEG2_L1 = [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256]
_BITRATES_MPEG2_L23 = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]

_SAMPLE_RATES = {
    3: [44100, 48000, 32000],
    2: [22050, 24000, 16000],
    0: [11025, 12000, 8000],
}

_VERSION_LABELS = {3: "MPEG1", 2: "MPEG2", 0: "MPEG2.5"}
_LAYER_LABELS = {1: "Layer III", 2: "Layer II", 3: "Layer I"}
_CHANNEL_MODES = {0: "stereo", 1: "joint stereo", 2: "dual channel", 3: "mono"}
_TEXT_FRAME_FIELDS = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TDRC": "year"}


class AudioInspector(BaseInspector):
    """MP3 inspector: parses ID3v2 tags and the first MPEG frame header.

    Standard-library only. Produces bitrate/sample rate/channel/format
    metadata plus ID3v2 title/artist/album and a CBR duration estimate from
    the recorded file size. Audio transcription is intentionally left to the
    audio grounding pipeline; this inspector performs no decoding.
    """

    media_category = MEDIA_CATEGORY_AUDIO
    supported_extensions = frozenset({".mp3"})
    supported_mime_types = frozenset({"audio/mpeg"})

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                header = buffer.read(_AUDIO_HEADER_WINDOW)
                return _inspect(header, file.file_size)
            except (struct.error, ValueError) as exc:
                raise InspectionError("audio file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _inspect(header: bytes, file_size: int) -> tuple[None, dict]:
    if not header:
        raise ValueError("empty audio file")

    offset = 0
    tags: dict[str, str | int] = {}
    if header[:3] == b"ID3":
        id3_size = _syncsafe(header[6:10])
        tags = _parse_id3v2(header[: min(len(header), 10 + id3_size)])
        offset = 10 + id3_size

    frame = _find_frame(header, offset)
    if frame is None:
        raise ValueError("no MPEG audio frame found")

    version = (frame >> 19) & 0b11
    layer = (frame >> 17) & 0b11
    bitrate_index = (frame >> 12) & 0b1111
    sample_index = (frame >> 10) & 0b11
    mode = (frame >> 6) & 0b11

    if version == 1 or layer == 0 or bitrate_index in (0, 15):
        raise ValueError("reserved MPEG frame header fields")

    bitrate_kbps = _bitrate(version, layer, bitrate_index)
    sample_rate = _SAMPLE_RATES[version][sample_index]

    return None, {
        "format": "mp3",
        "version": _VERSION_LABELS[version],
        "layer": _LAYER_LABELS[layer],
        "bitrate_kbps": bitrate_kbps,
        "sample_rate_hz": sample_rate,
        "channels": 1 if mode == 3 else 2,
        "channel_mode": _CHANNEL_MODES[mode],
        "duration_estimate_seconds": round(file_size * 8 / (bitrate_kbps * 1000), 2)
        if bitrate_kbps
        else None,
        **tags,
    }


def _syncsafe(raw: bytes) -> int:
    return (
        ((raw[0] & 0x7F) << 21)
        | ((raw[1] & 0x7F) << 14)
        | ((raw[2] & 0x7F) << 7)
        | (raw[3] & 0x7F)
    )


def _bitrate(version: int, layer: int, index: int) -> int:
    table = None
    if layer == 3:
        table = _BITRATES_MPEG1_L1 if version == 3 else _BITRATES_MPEG2_L1
    elif layer == 2:
        table = _BITRATES_MPEG1_L2 if version == 3 else _BITRATES_MPEG2_L23
    elif layer == 1:
        table = _BITRATES_MPEG1_L3 if version == 3 else _BITRATES_MPEG2_L23
    return table[index - 1]


def _find_frame(header: bytes, start: int) -> int | None:
    i = start
    while i + 4 <= len(header):
        if header[i] != 0xFF or (header[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        candidate = struct.unpack(">I", header[i:i + 4])[0]
        version = (candidate >> 19) & 0b11
        layer = (candidate >> 17) & 0b11
        bitrate_index = (candidate >> 12) & 0b1111
        sample_index = (candidate >> 10) & 0b11
        if (
            version != 1
            and layer != 0
            and bitrate_index not in (0, 15)
            and sample_index != 3
        ):
            return candidate
        i += 1
    return None


def _parse_id3v2(data: bytes) -> dict:
    if len(data) < 10 or data[:3] != b"ID3":
        return {}
    version_major = data[3]
    size = _syncsafe(data[6:10])
    tags: dict[str, str] = {}
    if version_major == 3:
        try:
            frame_end = min(len(data), 10 + size)
            _parse_id3v2_3_frames(data, tags, 10, frame_end)
        except (struct.error, IndexError):
            pass
    return tags


def _parse_id3v2_3_frames(data: bytes, tags: dict[str, str], start: int, end: int) -> None:
    pos = start
    while pos + 10 <= end:
        frame_id = data[pos:pos + 4]
        if not frame_id or any(c == 0 for c in frame_id):
            break
        frame_size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        frame_id_text = frame_id.decode("latin-1")
        if frame_id_text in _TEXT_FRAME_FIELDS and frame_size > 1 and pos + 10 + frame_size <= end:
            payload = data[pos + 10:pos + 10 + frame_size]
            value = _decode_text(payload)
            if value:
                tags[_TEXT_FRAME_FIELDS[frame_id_text]] = value
        if frame_size == 0:
            break
        pos += 10 + frame_size


def _decode_text(payload: bytes) -> str:
    enc = payload[0]
    body = payload[1:]
    if enc == 0:
        return body.decode("latin-1").strip("\x00 \t")
    if enc == 3:
        return body.decode("utf-8", errors="replace").strip("\x00 \t")
    if enc == 1:
        return body.decode("utf-16", errors="replace").strip("\x00 \t")
    if enc == 2:
        return body.decode("utf-16-be", errors="replace").strip("\x00 \t")
    return ""