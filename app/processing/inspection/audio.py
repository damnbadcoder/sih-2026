import struct

from app.core.formats import MEDIA_CATEGORY_AUDIO
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer

_AUDIO_HEADER_WINDOW = 1024 * 1024
_OGG_TAIL_WINDOW = 64 * 1024

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
_WAV_FORMAT_NAMES = {
    3: "IEEE float",
    6: "A-law",
    7: "mu-law",
    0x0034: "Dolby AC3",
    0x0161: "MPEG audio",
    0x566F: "Opus",
}


class AudioInspector(BaseInspector):
    """Audio inspector: MP3/WAV/FLAC/Ogg/M4A header metadata, stdlib or ISO-BMFF.

    Deterministic metadata only (format, sample rate, channels, bit depth and
    a size/granule-based duration estimate) — no decoding, no transcription.
    The MP3 branch parses ID3v2 tags and the first MPEG frame header; WAV/FLAC
    parse their container headers; Ogg reads the Vorbis identification header
    plus the last page's granule position for a duration estimate; M4A reuses
    the ISO-BMFF box reader. Audio transcription is intentionally left to the
    audio grounding pipeline.
    """

    media_category = MEDIA_CATEGORY_AUDIO
    supported_extensions = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a"})
    supported_mime_types = frozenset(
        {
            "audio/mpeg",
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "audio/flac",
            "audio/x-flac",
            "audio/ogg",
            "application/ogg",
            "audio/vorbis",
            "audio/mp4",
            "audio/x-m4a",
            "audio/x-m4b",
        }
    )

    async def _extract(self, file, storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                ext = _extension(file.original_filename)
                if ext == "m4a":
                    return _parse_m4a(buffer)
                header = buffer.read(_AUDIO_HEADER_WINDOW)
                tail = _read_tail(buffer)
                return _inspect(header, file.file_size, ext, tail)
            except (struct.error, ValueError, IndexError) as exc:
                raise InspectionError("audio file is malformed or unreadable") from exc
        finally:
            buffer.close()


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _read_tail(buffer) -> bytes | None:
    """Return the last ``_OGG_TAIL_WINDOW`` bytes for Ogg granule lookups."""
    current = buffer.tell()
    buffer.seek(0, 2)
    end = buffer.tell()
    buffer.seek(current)
    if end <= _AUDIO_HEADER_WINDOW:
        return None
    buffer.seek(-_OGG_TAIL_WINDOW, 2)
    tail = buffer.read()
    buffer.seek(current)
    return tail


def _inspect(header: bytes, file_size: int, ext: str, tail: bytes | None) -> tuple[None, dict]:
    if not header:
        raise ValueError("empty audio file")
    if ext == "wav":
        return _parse_wav(header, file_size)
    if ext == "flac":
        return _parse_flac(header)
    if ext == "ogg":
        return _parse_ogg(header, tail)
    return _parse_mp3(header, file_size)


def _parse_mp3(header: bytes, file_size: int) -> tuple[None, dict]:
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


def _parse_wav(header: bytes, _file_size: int) -> tuple[None, dict]:
    if len(header) < 44 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise ValueError("WAV RIFF signature missing")
    fmt: dict | None = None
    data_size: int | None = None
    pos = 12
    while pos + 8 <= len(header):
        chunk_id = header[pos:pos + 4]
        chunk_size = struct.unpack("<I", header[pos + 4:pos + 8])[0]
        if chunk_id == b"fmt ":
            if chunk_size < 16 or pos + 24 > len(header):
                raise ValueError("WAV fmt chunk truncated")
            fmt = {
                "audio_format": struct.unpack("<H", header[pos + 8:pos + 10])[0],
                "channels": struct.unpack("<H", header[pos + 10:pos + 12])[0],
                "sample_rate": struct.unpack("<I", header[pos + 12:pos + 16])[0],
                "byte_rate": struct.unpack("<I", header[pos + 16:pos + 20])[0],
                "bit_depth": struct.unpack("<H", header[pos + 22:pos + 24])[0],
            }
        elif chunk_id == b"data":
            data_size = chunk_size
            break
        pos += 8 + chunk_size + (chunk_size & 1)
    if fmt is None or data_size is None:
        raise ValueError("WAV missing fmt or data chunk")

    byte_rate = fmt["byte_rate"]
    metadata: dict = {
        "format": "wav",
        "channels": fmt["channels"],
        "sample_rate_hz": fmt["sample_rate"],
        "bit_depth": fmt["bit_depth"],
        "duration_estimate_seconds": round(data_size / byte_rate, 2) if byte_rate else None,
    }
    audio_format = fmt["audio_format"]
    if audio_format not in (1, 0xFFFE):  # PCM or extensible: label only non-PCM codecs
        metadata["compression"] = _WAV_FORMAT_NAMES.get(
            audio_format, f"unknown({audio_format})"
        )
    return None, metadata


def _parse_flac(header: bytes) -> tuple[None, dict]:
    if header[:4] != b"fLaC":
        raise ValueError("FLAC signature missing")
    pos = 4
    while pos + 4 <= len(header):
        meta_type = header[pos] & 0x7F
        last = header[pos] >> 7
        length = int.from_bytes(header[pos + 1:pos + 4], "big")
        payload = header[pos + 4:pos + 4 + length]
        if len(payload) < length:
            raise ValueError("FLAC metadata block truncated")
        if meta_type == 0:
            if len(payload) < 18:
                raise ValueError("FLAC STREAMINFO truncated")
            value = int.from_bytes(payload[10:18], "big")
            sample_rate = (value >> 44) & 0xFFFFF
            channels = ((value >> 41) & 0x07) + 1
            bit_depth = ((value >> 36) & 0x1F) + 1
            total_samples = value & 0xFFFFFFFFF
            return None, {
                "format": "flac",
                "sample_rate_hz": sample_rate,
                "channels": channels,
                "bit_depth": bit_depth,
                "total_samples": total_samples,
                "duration_estimate_seconds": round(total_samples / sample_rate, 2)
                if sample_rate
                else None,
            }
        pos += 4 + length
        if last:
            break
    raise ValueError("FLAC STREAMINFO block missing")


def _parse_ogg(header: bytes, tail: bytes | None) -> tuple[None, dict]:
    capture = header.find(b"\x01vorbis")
    if capture < 0:
        raise ValueError("Ogg Vorbis capture pattern missing")
    pos = capture + 7
    if pos + 30 > len(header):
        raise ValueError("Ogg Vorbis identification header truncated")
    if struct.unpack("<I", header[pos:pos + 4])[0] != 0:
        raise ValueError("unsupported Ogg Vorbis version")
    channels = header[pos + 4]
    sample_rate = struct.unpack("<I", header[pos + 5:pos + 9])[0]
    bitrate_nominal = struct.unpack("<I", header[pos + 13:pos + 17])[0]

    total_samples = _last_page_granule(header if tail is None else tail)
    metadata: dict = {
        "format": "ogg",
        "codec": "vorbis",
        "channels": channels,
        "sample_rate_hz": sample_rate,
        "duration_estimate_seconds": round(total_samples / sample_rate, 2)
        if total_samples is not None and sample_rate
        else None,
    }
    if bitrate_nominal:
        metadata["bitrate_nominal"] = bitrate_nominal
    return None, metadata


def _last_page_granule(data: bytes) -> int | None:
    """Best-effort final Ogg page granule position (deterministic)."""
    granule = None
    search_from = 0
    while True:
        marker = data.find(b"OggS", search_from)
        if marker < 0 or marker + 14 > len(data):
            break
        if data[marker + 4] == 0:  # version byte
            granule = struct.unpack("<Q", data[marker + 6:marker + 14])[0]
        search_from = marker + 4
    return granule


def _parse_m4a(buffer) -> tuple[None, dict]:
    from app.processing.inspection.video import (
        BoxStructureError,
        _BoxReader,
        _parse_container,
    )

    reader = _BoxReader(buffer)
    info: dict = {"brand": None, "duration": None, "handlers": set(), "width": None, "height": None}

    first = reader.box()
    if first is None or first[1] != b"ftyp":
        raise BoxStructureError("M4A FTYP box missing")
    size, _box_type, header_len = first
    info["brand"] = reader._take(4).decode("ascii", errors="replace") or "m4a"
    reader._file.seek(size - header_len - 4, 1)

    while True:
        box = reader.box()
        if box is None:
            break
        size, box_type, header_len = box
        if box_type == b"moov":
            _parse_container(reader, size, header_len, info)
        else:
            reader._file.seek(size - header_len, 1)

    duration = info["duration"]
    return None, {
        "format": "m4a",
        "brand": info["brand"] or "m4a",
        "duration_seconds": round(duration, 2) if duration is not None else None,
        "has_audio": "soun" in info["handlers"],
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