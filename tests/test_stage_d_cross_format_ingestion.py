import glob
import io
import json
import struct
import subprocess
import tempfile
import uuid
import wave
import zipfile
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path

import pytest
from docx import Document as _DocxDocument
from httpx import ASGITransport, AsyncClient
from pptx import Presentation as _PptxPresentation
from sqlalchemy import delete, select

from app.config import get_settings
from app.core.formats import (
    EXTENSION_CATEGORIES,
    MEDIA_CATEGORY_UNKNOWN,
    classify_format,
)
from app.core.uploads import ALLOWED_UPLOAD_TYPES, normalize_filename
from app.db.session import async_session_factory
from app.main import app
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing.inspection import (
    InspectionError,
    get_inspector,
    legacy_office,
)
from app.processing.inspection.registry import _INSPECTORS
from app.processing.normalization import iter_normalized_records
from app.processing.service import (
    process_job,
    reserve_job_for_processing,
)
from app.schemas.transformation import TransformationCreateRequest
from app.services.grounding import GroundingService
from app.services.transformations import OwnershipError, TransformationService
from app.storage import get_storage
from app.storage.local import LocalStorage

CREATED_EMAILS: list[str] = []

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_METADATA_ONLY_FORMATS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif",
        ".mp3", ".wav", ".m4a", ".ogg", ".flac",
        ".mp4", ".mkv", ".mov", ".avi", ".webm",
    }
)

_SOFFICE_BINARY = legacy_office._libreoffice_binary()
_HEADLESS_ARGS = legacy_office._HEADLESS_ARGS
_EVTX_FIXTURE = Path(__file__).parent / "fixtures" / "evtx" / "issue_38.evtx"


def _soffice_available() -> bool:
    return _SOFFICE_BINARY is not None


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def cleanup_created_users() -> None:
    if not CREATED_EMAILS:
        return
    async with async_session_factory() as db:
        await db.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))
        await db.commit()
    CREATED_EMAILS.clear()


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    store = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
async def client(storage):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await cleanup_created_users()


# --- sample builders (all 46 formats) -----------------------------------------


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", 0)


def _box(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + tag + payload


def _png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 640, 480, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", b"")
        + _chunk(b"IEND", b"")
    )


def _jpg() -> bytes:
    app0 = struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", 480, 640) + b"\x03"
    return b"\xff\xd8\xff\xe0" + app0 + b"\xff\xc0" + sof0 + b"\xff\xd9"


def _bmp() -> bytes:
    width, height, bd, pixel_offset = 320, 240, 24, 54
    row_size = (width * bd // 8 + 3) & ~3
    file_size = pixel_offset + row_size * height
    file_header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, pixel_offset)
    info_header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, bd, 0, 0, 0, 0, 0, 0)
    return file_header + info_header + b"\x00" * (row_size * height)


def _webp() -> bytes:
    packed = (320 - 1) | ((200 - 1) << 14)
    payload = b"\x2f" + struct.pack("<I", packed)
    chunk = b"VP8L" + struct.pack("<I", len(payload)) + payload + b"\x00"
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def _tiff_entry(tag: int, field_type: int, value: int) -> bytes:
    return struct.pack("<HHII", tag, field_type, 1, value)


def _tiff() -> bytes:
    entries = (
        _tiff_entry(256, 4, 320) + _tiff_entry(257, 4, 240)
        + _tiff_entry(258, 3, 8) + _tiff_entry(259, 3, 1) + _tiff_entry(262, 3, 2)
    )
    return (
        b"II"
        + struct.pack("<H", 42)
        + struct.pack("<I", 8)
        + struct.pack("<H", 5)
        + entries
        + struct.pack("<I", 0)
    )


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\x00\x00" * 8000)
    return buf.getvalue()


def _syncsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _mp3() -> bytes:
    payload = b"\x00Nocturne"
    frame = b"TIT2" + struct.pack(">I", len(payload)) + b"\x00\x00" + payload
    id3 = b"ID3\x03\x00\x00" + _syncsafe(len(frame)) + frame
    return id3 + struct.pack(">I", 0xFFFB9000) + b"\x00" * 8192


def _flac() -> bytes:
    value = (44100 << 44) | (1 << 41) | (15 << 36) | 441000
    streaminfo = (
        struct.pack(">HH", 4096, 4096)
        + b"\x00" * 6
        + value.to_bytes(8, "big")
        + b"\x00" * 16
    )
    return b"fLaC" + b"\x80\x00\x00\x22" + streaminfo


def _ogg() -> bytes:
    ident = (
        struct.pack("<I", 0) + bytes([2]) + struct.pack("<I", 44100)
        + struct.pack("<I", 0) + struct.pack("<I", 160000) + struct.pack("<I", 0)
        + bytes([0xB0]) + bytes([1])
    )
    first_payload = b"\x01vorbis" + ident
    first_page = (
        b"OggS\x00\x00" + struct.pack("<Q", 0) + struct.pack("<I", 1)
        + struct.pack("<I", 0) + struct.pack("<I", 0) + b"\x02\x07\x1e" + first_payload
    )
    return first_page + b"\x00" * 64


def _moov(handler: bytes) -> bytes:
    mvhd = _box(
        b"mvhd",
        b"\x00\x00\x00\x00" + struct.pack(">I", 0) + struct.pack(">I", 0)
        + struct.pack(">I", 1000) + struct.pack(">I", 3000),
    )
    hdlr = _box(b"hdlr", b"\x00\x00\x00\x00\x00\x00\x00\x00" + handler + b"\x00" * 12)
    return _box(b"moov", _box(b"trak", mvhd + _box(b"mdia", hdlr)))


def _mp4() -> bytes:
    return _box(b"ftyp", b"isom\x00\x00\x00\x00isomiso2") + _moov(b"vide")


def _mov() -> bytes:
    return _box(b"ftyp", b"isom\x00\x00\x00\x00qt  ") + _moov(b"vide")


def _m4a() -> bytes:
    return _box(b"ftyp", b"isom\x00\x00\x00\x00qt  ") + _moov(b"soun")


def _ebml_size(n: int) -> bytes:
    if n < 0x80:
        return bytes([0x80 | n])
    if n < 0x4000:
        return bytes([0x40 | (n >> 8), n & 0xFF])
    return bytes([0x20 | (n >> 16), (n >> 8) & 0xFF, n & 0xFF])


def _ebml_element(eid: bytes, payload: bytes) -> bytes:
    return eid + _ebml_size(len(payload)) + payload


def _mkv(doctype: bytes = b"matroska") -> bytes:
    ebml = _ebml_element(
        b"\x1a\x45\xdf\xa3",
        _ebml_element(b"\x42\x86", b"\x01")
        + _ebml_element(b"\x42\x82", doctype)
        + _ebml_element(b"\x42\x87", b"\x02"),
    )
    info = _ebml_element(
        b"\x15\x49\xa9\x66",
        _ebml_element(b"\x2a\xd7\xb1", (1_000_000).to_bytes(4, "big"))
        + _ebml_element(b"\x44\x89", struct.pack(">d", 5500.0)),
    )
    video = _ebml_element(
        b"\xe0", _ebml_element(b"\xb0", b"\x02\x80") + _ebml_element(b"\xba", b"\x01\xe0")
    )
    video_track = _ebml_element(
        b"\xae", _ebml_element(b"\x83", b"\x01") + _ebml_element(b"\x86", b"V_VP9") + video
    )
    tracks = _ebml_element(b"\x16\x54\xae\x6b", video_track)
    return ebml + _ebml_element(b"\x18\x53\x80\x67", info + tracks)


def _riff_chunk(cc: bytes, payload: bytes) -> bytes:
    pad = b"\x00" if len(payload) % 2 else b""
    return cc + struct.pack("<I", len(payload)) + payload + pad


def _avi() -> bytes:
    width, height, frames = 320, 240, 1000
    avih = _riff_chunk(
        b"avih", struct.pack("<IIIIIIIIIIII", 40000, 0, 0, 0, frames, 0, 1, 0, width, height, 0, 0)
    )
    strh = _riff_chunk(
        b"strh",
        b"vidsDIB "
        + struct.pack("<IHHIIIIIIII", 0, 0, 0, 0, 1, 25, 0, frames, 0, 0, 0)
        + struct.pack("<iiii", 0, 0, 0, 0),
    )
    strf = _riff_chunk(
        b"strf", struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, 0, 0, 0, 0, 0)
    )
    strl = b"LIST" + struct.pack("<I", 4 + len(strh) + len(strf)) + b"strl" + strh + strf
    hdrl = b"LIST" + struct.pack("<I", 4 + len(avih) + len(strl)) + b"hdrl" + avih + strl
    return b"RIFF" + struct.pack("<I", 4 + len(hdrl)) + b"AVI " + hdrl


def _xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            "<?xml version='1.0'?><sst xmlns='http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main'><si><t>Alpha</t></si><si><t>Beta</t></si></sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            "<?xml version='1.0'?><worksheet xmlns='http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main'><sheetData>"
            "<row r='1'><c r='A1' t='s'><v>0</v></c><c r='B1'><v>7</v></c></row>"
            "</sheetData></worksheet>",
        )
    return buf.getvalue()


def _xls() -> bytes:
    from xlwt import Workbook

    workbook = Workbook()
    sheet = workbook.add_sheet("Alerts")
    sheet.write(0, 0, "host")
    sheet.write(0, 1, "count")
    sheet.write(1, 0, "srv-01")
    sheet.write(1, 1, 42)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _pdf(texts: list[str] | None = None) -> bytes:
    texts = texts or ["Event IOC 203.0.113.7"]

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    count = len(texts)

    def page_idx(i: int) -> int:
        return 3 + 2 * i

    def contents_idx(i: int) -> int:
        return 4 + 2 * i

    font_idx = 3 + 2 * count
    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        (
            f"2 0 obj\n<< /Type /Pages /Kids ["
            f"{' '.join(f'{page_idx(i)} 0 R' for i in range(count))}"
            f"] /Count {count} >>\nendobj\n"
        ).encode(),
    ]
    for i in range(count):
        objects.append(
            (
                f"{page_idx(i)} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {contents_idx(i)} 0 R "
                f"/Resources << /Font << /F1 {font_idx} 0 R >> >> >>\n"
                f"endobj\n"
            ).encode()
        )
    for i, text in enumerate(texts):
        content = f"BT /F1 20 Tf 72 720 Td ({esc(text)}) Tj ET\n".encode()
        objects.append(
            (
                f"{contents_idx(i)} 0 obj\n<< /Length {len(content)} >>\n"
                f"stream\n{content.decode()}\nendstream\nendobj\n"
            ).encode()
        )
    objects.append(
        (
            f"{font_idx} 0 obj\n"
            f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
            f"endobj\n"
        ).encode()
    )

    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    cursor = 0
    offsets: list[int] = []
    for obj in objects:
        offsets.append(cursor)
        cursor += len(obj)
    xref_pos = len(header) + cursor
    entries = [b"0000000000 65535 f \n"]
    entries.extend(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    trailer = (
        f"trailer\n<< /Size {font_idx + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return header + body + f"xref\n0 {len(entries)}\n".encode() + b"".join(entries) + trailer


def _docx(paragraphs: list[str] | None = None) -> bytes:
    document = _DocxDocument()
    for paragraph in paragraphs or ["Alert IOC CVE-2026-0001"]:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pptx(lines: list[str] | None = None) -> bytes:
    prs = _PptxPresentation()
    blank = prs.slide_layouts[6]
    for line in lines or ["Threat deck"]:
        slide = prs.slides.add_slide(blank)
        textbox = slide.shapes.add_textbox(0, 0, 200, 100)
        textbox.text = line
    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _svg(body: str = "C2 203.0.113.9") -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" '
        b'viewBox="0 0 640 480"><text>' + body.encode() + b"</text></svg>"
    )


def _through_soffice(source: bytes, target_ext: str) -> bytes:
    if not _soffice_available():
        pytest.skip("LibreOffice required to build legacy fixtures")
    with tempfile.TemporaryDirectory(prefix="office_fixture_") as workdir:
        work = Path(workdir)
        src = work / "input"
        src.write_bytes(source)
        out = work / "out"
        out.mkdir()
        profile = work / "profile"
        profile.mkdir()
        cmd = [
            _SOFFICE_BINARY,
            *_HEADLESS_ARGS,
            "-env:UserInstallation=file://" + profile.as_posix(),
            "--convert-to",
            target_ext,
            "--outdir",
            str(out),
            str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")
        outputs = list(out.glob("*"))
        assert len(outputs) == 1, f"expected a single converted fixture, got {outputs!r}"
        return outputs[0].read_bytes()


@lru_cache(maxsize=2)
def _doc_fixture() -> bytes:
    return _through_soffice(_docx(["Legacy document IOC"]), "doc")


@lru_cache(maxsize=2)
def _ppt_fixture() -> bytes:
    return _through_soffice(_pptx(["Legacy deck IOC"]), "ppt")


_TEXT_SAMPLES: dict[str, bytes | None] = {
    ".txt": b"plain event text 203.0.113.7\n",
    ".md": b"# note\n\nCVE-2026-0001\n",
    ".markdown": b"markdown body\n",
    ".csv": b"host,count\nsrv-01,7\n",
    ".tsv": b"host\tcount\nsrv-01\t7\n",
    ".json": b'{"host": "srv-01"}',
    ".jsonl": b'{"host": "a"}\n{"host": "b"}\n',
    ".log": b"2026-09-12T10:00:00Z host sshd Accept password for admin from 203.0.113.7\n",
    ".syslog": b"Sep 12 10:00:00 host service[1]: event 203.0.113.7\n",
    ".yara": b'rule alert_demo {\n  strings:\n    $a = "CVE-2026-0001"\n  condition:\n    $a\n}\n',
    ".sigma": b"title: test\ndetection:\n  selection:\n    a: b\n  condition: selection\n",
    ".xml": b'<?xml version="1.0"?><root><item>ioc 203.0.113.7</item></root>',
    ".rss": (
        b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0">'
        b"<channel><title>feed</title><item><title>alert A</title></item></channel></rss>"
    ),
    ".atom": (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom">'
        b"<title>feed</title><entry><title>alert B</title></entry></feed>"
    ),
    ".stix": b'{"type": "indicator", "name": "t1"}',
    ".taxii": b'{"data": {"objects": []}}',
    ".yaml": b"host: srv-01\n",
    ".yml": b"host: srv-01\n",
    ".py": b'print("hello")\n',
    ".sh": b"#!/bin/sh\necho hi\n",
    ".ps1": b'Write-Host "hi"\n',
}

_BINARY_SAMPLES: dict[str, object] = {
    ".pdf": _pdf,
    ".docx": _docx,
    ".doc": _doc_fixture,
    ".pptx": _pptx,
    ".ppt": _ppt_fixture,
    ".xlsx": _xlsx,
    ".xls": _xls,
    ".rtf": lambda: b"{\\rtf1\\ansi\\pard Alert host srv-07\\par}",
    ".svg": _svg,
    ".png": _png,
    ".jpg": _jpg,
    ".jpeg": _jpg,
    ".webp": _webp,
    ".bmp": _bmp,
    ".tiff": _tiff,
    ".tif": _tiff,
    ".mp3": _mp3,
    ".wav": _wav,
    ".m4a": _m4a,
    ".ogg": _ogg,
    ".flac": _flac,
    ".mp4": _mp4,
    ".mkv": _mkv,
    ".mov": _mov,
    ".avi": _avi,
    ".webm": lambda: _mkv(b"webm"),
    ".evtx": lambda: _EVTX_FIXTURE.read_bytes(),
}


def _sample(ext: str) -> bytes:
    if ext in _TEXT_SAMPLES:
        assert _TEXT_SAMPLES[ext] is not None
        return _TEXT_SAMPLES[ext]
    builder = _BINARY_SAMPLES.get(ext)
    if builder is not None:
        return builder() if callable(builder) else builder
    raise AssertionError(f"missing sample builder for {ext}")


async def _write_via_storage(storage: LocalStorage, input_file: InputFile, data: bytes) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield data

    await storage.save(chunks(), input_file.storage_path, max_size=len(data) + 1)


def make_input_file(filename: str, content_type: str, data: bytes) -> InputFile:
    return InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename=filename,
        stored_filename=f"stored_{filename}",
        content_type=content_type,
        file_size=len(data),
        storage_path=f"{uuid.uuid4()}/job/{filename}",
    )


async def _inspect(storage: LocalStorage, filename: str, data: bytes):
    content_type = ALLOWED_UPLOAD_TYPES["." + filename.rsplit(".", 1)[1]]
    input_file = make_input_file(filename, content_type, data)
    await _write_via_storage(storage, input_file, data)
    inspector = get_inspector(classify_format(filename, content_type))
    return await inspector.inspect(input_file, storage)


# --- 46-format registry contract ----------------------------------------------


def test_contract_exactly_46_formats():
    assert len(ALLOWED_UPLOAD_TYPES) == 46


def test_contract_every_allowed_extension_claimed_by_exactly_one_inspector():
    claimed: dict[str, list[str]] = {}
    for inspectors in _INSPECTORS.values():
        for inspector in inspectors:
            for extension in inspector.supported_extensions:
                claimed.setdefault(extension, []).append(type(inspector).__name__)

    assert set(ALLOWED_UPLOAD_TYPES) == set(claimed)
    conflicts = {extension: names for extension, names in claimed.items() if len(names) > 1}
    assert conflicts == {}
    for extension in ALLOWED_UPLOAD_TYPES:
        classification = classify_format(
            f"sample{extension}", ALLOWED_UPLOAD_TYPES[extension]
        )
        inspector = get_inspector(classification)
        assert inspector is not None
        assert extension in inspector.supported_extensions


def test_contract_resolution_is_deterministic_and_category_consistent():
    settings = get_settings()
    assert settings.MAX_UPLOAD_SIZE_BYTES == 25 * 1024 * 1024
    for extension, canonical in ALLOWED_UPLOAD_TYPES.items():
        classification = classify_format(f"report{extension}", canonical)
        first = get_inspector(classification)
        second = get_inspector(classification)
        assert first is second is not None
        assert classification.media_category == EXTENSION_CATEGORIES[extension]
        assert first.media_category == EXTENSION_CATEGORIES[extension]


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("report.json", "application/json", "TextInspector"),
        ("ioc.stix", "application/json", "MarkupInspector"),
        ("bundle.taxii", "application/json", "MarkupInspector"),
        ("rule.sigma", "text/yaml", "SigmaInspector"),
        ("conf.yaml", "text/yaml", "SigmaInspector"),
        ("conf.yml", "text/yaml", "SigmaInspector"),
        ("doc.md", "text/markdown", "TextInspector"),
        ("notes.txt", "text/plain", "TextInspector"),
        ("photo.png", "image/jpeg", "ImageInspector"),
        ("photo.jpg", "image/png", "ImageInspector"),
        ("clip.mkv", "video/webm", "VideoInspector"),
        ("clip.webm", "video/x-matroska", "VideoInspector"),
    ],
)
def test_contract_extension_first_never_cross_routes_shared_mime(filename, content_type, expected):
    classification = classify_format(filename, content_type)
    inspector = get_inspector(classification)
    assert type(inspector).__name__ == expected


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("photo.png", "text/plain"),
        ("notes.txt", "image/png"),
        ("paper.pdf", "text/plain"),
        ("data.csv", "application/pdf"),
    ],
)
def test_contract_contradictory_mime_is_unknown_and_unroutable(filename, content_type):
    classification = classify_format(filename, content_type)
    assert classification.media_category is MEDIA_CATEGORY_UNKNOWN
    assert get_inspector(classification) is None


def test_contract_text_formats_never_claim_subset_extensions():
    text_inspectors = _INSPECTORS["text"]
    for extension in (".md", ".markdown", ".json", ".jsonl", ".txt", ".csv", ".tsv",
                      ".log", ".syslog", ".yara", ".py", ".sh", ".ps1"):
        matches = [
            type(inspector).__name__
            for inspector in text_inspectors
            if extension in inspector.supported_extensions
        ]
        assert matches, f"no inspector claims {extension}"
        assert len(matches) == 1, f"multiple inspectors claim {extension}: {matches}"


# --- metadata-only contract ----------------------------------------------------


@pytest.mark.parametrize("extension", sorted(_METADATA_ONLY_FORMATS))
async def test_metadata_only_media_never_fabricate_text(storage, extension):
    assert extension in ALLOWED_UPLOAD_TYPES
    data = _sample(extension)
    result = await _inspect(storage, f"sample{extension}", data)
    assert result.supported_for_inspection is True
    assert result.extracted_text is None
    record = next(iter_normalized_records([result]))
    assert record["supported_for_inspection"] is True
    assert record["normalized_text"] is None
    assert record["reason"] == "no extractable text"


def test_metadata_only_set_pins_exactly_seventeen_formats():
    metadata_only = {
        extension
        for extension in ALLOWED_UPLOAD_TYPES
        if "svg" not in extension
        and EXTENSION_CATEGORIES[extension] in ("image", "audio", "video")
    }
    assert metadata_only == _METADATA_ONLY_FORMATS
    assert len(_METADATA_ONLY_FORMATS) == 17


# --- malformed and adversarial hardening ---------------------------------------


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        (".png", b"\x89PNG\r\n\x1a\n"),
        (".pdf", b"%PDF-1.4"),
        (".xlsx", b"PK\x03\x04"),
        (".evtx", b""),
        (".xml", b"<root><a>"),
        (".json", b"{"),
        (".sigma", b"title: [unclosed"),
    ],
)
async def test_truncated_or_malformed_inputs_raise_controlled_error(storage, filename, data):
    with pytest.raises(InspectionError):
        await _inspect(storage, f"sample{filename}", data)


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        (".png", _jpg()),
        (".jpg", _png()),
        (".png", b"<html>junk</html>"),
    ],
)
async def test_content_signature_contradiction_rejected(storage, filename, data):
    with pytest.raises(InspectionError):
        await _inspect(storage, f"sample{filename}", data)


async def test_plain_text_family_survives_binary_content_without_failure(storage):
    result = await _inspect(storage, "sample.txt", b"\x00\xff some\x00 text \xfe\n")
    assert result.supported_for_inspection is True
    assert result.extracted_text is not None


@pytest.mark.parametrize(
    ("extension", "make_payload"),
    [
        (
            ".xml",
            lambda: b'<?xml version="1.0"?>'
            b'<!DOCTYPE root [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>'
            b"<root><data>&xxe;</data></root>",
        ),
        (
            ".rss",
            lambda: b'<?xml version="1.0"?>'
            b'<!DOCTYPE rss [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>'
            b"<rss><channel><title>&xxe;</title></channel></rss>",
        ),
        (
            ".svg",
            lambda: b'<?xml version="1.0"?>'
            b'<!DOCTYPE svg [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"><text>&xxe;</text></svg>',
        ),
    ],
)
async def test_file_entity_never_leaks_local_content(storage, extension, make_payload):
    result = await _inspect(storage, f"sample{extension}", make_payload())
    assert result.supported_for_inspection is True
    extracted = result.extracted_text or ""
    assert "root:" not in extracted
    assert "/etc/passwd" not in extracted
    assert "daemon" not in extracted


@pytest.mark.parametrize(
    ("extension",),
    [(e,) for e in (".xml", ".svg", ".rss")],
)
async def test_external_dtd_is_never_fetched(storage, extension):
    roots = {
        ".xml": b"<root><data>safe</data></root>",
        ".rss": b'<rss><channel><title>safe</title></channel></rss>',
        ".svg": b'<svg xmlns="http://www.w3.org/2000/svg"><text>safe</text></svg>',
    }
    payload = (
        b'<?xml version="1.0"?><!DOCTYPE root SYSTEM "http://evil.example/dtd">'
        + roots[extension]
    )
    result = await _inspect(storage, f"sample{extension}", payload)
    assert result.supported_for_inspection is True
    assert "evil.example" not in (result.extracted_text or "")


@pytest.mark.parametrize("extension", [".xml", ".svg"])
async def test_billion_laughs_payload_stays_bounded(storage, extension):
    root_tag = "svg" if extension == ".svg" else "root"
    payload = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE lolz [ <!ENTITY lol "lol">'
        b' <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b' <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;"> ]>\n'
        + f"<{root_tag}><data>&lol3;</data></{root_tag}>".encode()
    )
    result = await _inspect(storage, f"sample{extension}", payload)
    assert result.supported_for_inspection is True
    assert len(result.extracted_text or "") < 1000


# --- resource limits and runtime safety ---------------------------------------


def test_default_normalization_cap_tied_to_upload_cap():
    settings = get_settings()
    assert settings.MAX_UPLOAD_SIZE_BYTES == 25 * 1024 * 1024
    assert settings.MAX_UPLOAD_SIZE_BYTES == 26_214_400


def test_app_never_serves_uploaded_files_statically():
    from starlette.routing import Mount

    for route in app.routes:
        assert not isinstance(route, Mount)


@pytest.mark.skipif(not _soffice_available(), reason="LibreOffice not available")
async def test_libreoffice_conversion_uses_guarded_subprocess_kwargs(storage, monkeypatch):
    recorded: dict = {}
    real_run = legacy_office.subprocess.run

    def spy(*args, **kwargs):
        recorded["cmd"] = args[0]
        recorded.update(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(legacy_office.subprocess, "run", spy)
    result = await _inspect(storage, "sample.doc", _doc_fixture())
    assert result.supported_for_inspection is True
    assert recorded["timeout"] == 60
    assert recorded["start_new_session"] is True
    assert recorded["capture_output"] is True
    assert "--headless" in recorded["cmd"]
    assert Path(recorded["cmd"][-1]).name == "input"


async def test_evtx_inspection_leaves_no_temp_spool(storage):
    before = set(glob.glob("/tmp/evtx_*.evtx"))
    await _inspect(storage, "log.evtx", _EVTX_FIXTURE.read_bytes())
    after = set(glob.glob("/tmp/evtx_*.evtx"))
    assert after - before == set()


@pytest.mark.skipif(not _soffice_available(), reason="LibreOffice not available")
async def test_libreoffice_inspection_leaves_no_temp_workspace(storage):
    before = set(glob.glob(tempfile.gettempdir() + "/office_inspect_*"))
    await _inspect(storage, "memo.doc", _doc_fixture())
    after = set(glob.glob(tempfile.gettempdir() + "/office_inspect_*"))
    assert after - before == set()


# --- filename hardening --------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("normal.pdf", "normal.pdf"),
        (r"C:\Users\j\report.docx", "report.docx"),
        ("../../etc/passwd", "passwd"),
        ("evil\x00break.pdf", "evilbreak.pdf"),
        ("evil\r\ninject.txt", "evilinject.txt"),
        ("tab\tname.csv", "tabname.csv"),
        ("del\x7fchar.csv", "delchar.csv"),
        ("café.pdf", "café.pdf"),
        ("\x00\x01\x02", "upload"),
        ("  spaced.pdf  ", "spaced.pdf"),
    ],
)
def test_normalize_filename_strips_directory_controls_and_keeps_unicode(filename, expected):
    assert normalize_filename(filename) == expected


async def test_upload_with_hostile_filename_is_sanitized_at_ingest(client):
    email = unique_email("d_nul")
    CREATED_EMAILS.append(email)
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    job = await client.post("/api/v1/jobs", json={"config": {}}, headers=headers)
    job_id = job.json()["id"]

    hostile = "..\\..\\evil\x00\t\x1f.inject.pdf"
    boundary = "sih-d-boundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="',
            hostile.encode("latin-1"),
            b'"\r\n',
            b"Content-Type: application/pdf\r\n\r\n",
            b"%PDF-1.4-end",
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    response = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **headers},
    )
    assert response.status_code == 201, response.text
    assert response.json()["original_filename"] == "evil.inject.pdf"

    async with async_session_factory() as db:
        row = await db.scalar(
            select(InputFile).where(InputFile.job_id == uuid.UUID(job_id))
        )
        assert row.original_filename == "evil.inject.pdf"
        assert all(ord(ch) >= 32 and ch != "\x7f" for ch in row.original_filename)
        assert "/" not in row.stored_filename
        assert "\\" not in row.stored_filename
        assert row.storage_path.startswith("/") is False


# --- normalization integration --------------------------------------------------


async def test_inspectors_emit_raw_text_and_normalization_is_the_single_boundary(storage):
    raw = "cafe\u0301  \r\nhost srv-0\u03017  trailing  \n"
    result = await _inspect(storage, "sample.txt", raw.encode("utf-8"))
    assert result.supported_for_inspection is True
    assert result.extracted_text == raw
    assert "\r\n" in result.extracted_text
    assert "\u0301" in result.extracted_text

    record = next(iter_normalized_records([result]))
    assert record["normalized_text"] == "café\nhost srv-0\u03017  trailing\n"
    assert "\r" not in record["normalized_text"]
    assert record["reason"] is None


async def test_document_inspector_text_feeds_same_normalization_boundary(storage):
    result = await _inspect(storage, "memo.docx", _docx(["Line one  ", "\tsecond\tline"]))
    record = next(iter_normalized_records([result]))
    assert record["normalized_text"] == "Line one\n\tsecond\tline\n"
    assert record["supported_for_inspection"] is True


# --- grounding and source ingestion integration --------------------------------


async def _make_user(prefix: str) -> User:
    email = unique_email(prefix)
    CREATED_EMAILS.append(email)
    async with async_session_factory() as db:
        user = User(email=email, password_hash="test-hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _chunks(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


async def test_grounding_mixed_file_sources_document_plus_media(storage):
    owner = await _make_user("stage_d_mixed")
    async with async_session_factory() as db:
        job = Job(user_id=owner.id, status="created")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        source_specs = [
            ("memo.docx", _docx(["Critical CVE-2026-0001 at 203.0.113.7."]), _DOCX_MIME),
            ("photo.png", _png(), "image/png"),
        ]
        file_ids = []
        for original, data, content_type in source_specs:
            storage_path = f"{owner.id}/{job.id}/input/{original}"
            await storage.save(_chunks(data), storage_path, max_size=len(data) + 1)
            input_file = InputFile(
                job_id=job.id,
                original_filename=original,
                stored_filename=original,
                content_type=content_type,
                file_size=len(data),
                storage_path=storage_path,
            )
            db.add(input_file)
            await db.commit()
            await db.refresh(input_file)
            file_ids.append(input_file.id)

        payload = TransformationCreateRequest(
            title="stage-d-mixed",
            outputs=[{"outputType": "advisory"}],
            sources=[{"source_type": "file", "input_file_id": file_id} for file_id in file_ids],
        )
        transformation = await TransformationService().create_transformation(db, owner, payload)
        context = await GroundingService(storage).build_context(transformation)

    assert len(context.sources) == 2
    document = next(
        s for s in context.sources if s.source_type == "file" and s.media_category == "document"
    )
    media = next(
        s for s in context.sources if s.source_type == "file" and s.media_category == "image"
    )
    assert "CVE-2026-0001" in document.normalized_text
    assert media.normalized_text is None
    assert media.iocs == {}
    assert media.reason == "no extractable text"
    assert context.indicators["cve"] == ["CVE-2026-0001"]
    assert context.indicators["ipv4"] == ["203.0.113.7"]
    assert any(source.iocs == {} and source.reason for source in context.sources)


async def test_source_ingestion_rejects_cross_tenant_file(storage):
    owner_a = await _make_user("stage_d_owner_a")
    owner_b = await _make_user("stage_d_owner_b")

    async with async_session_factory() as db:
        job = Job(user_id=owner_a.id, status="created")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        storage_path = f"{owner_a.id}/{job.id}/input/secret.txt"
        await storage.save(_chunks(b"secret"), storage_path, max_size=4 * 1024)
        input_file = InputFile(
            job_id=job.id,
            original_filename="secret.txt",
            stored_filename="secret.txt",
            content_type="text/plain",
            file_size=6,
            storage_path=storage_path,
        )
        db.add(input_file)
        await db.commit()
        await db.refresh(input_file)
        foreign_id = input_file.id

        payload = TransformationCreateRequest(
            title="sneak",
            outputs=[{"outputType": "advisory"}],
            sources=[{"source_type": "file", "input_file_id": foreign_id}],
        )
        with pytest.raises(OwnershipError):
            await TransformationService().create_transformation(db, owner_b, payload)


# --- cross-stage end-to-end ingestion (all 46) ---------------------------------


def _upload_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_all_46_formats_ingest_end_to_end(client, storage):
    email = unique_email("stage_d_46")
    CREATED_EMAILS.append(email)
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    token = login.json()["access_token"]
    headers = _upload_headers(token)
    job = await client.post("/api/v1/jobs", json={"config": {}}, headers=headers)
    job_id = job.json()["id"]

    uploaded = []
    for extension, content_type in ALLOWED_UPLOAD_TYPES.items():
        filename = f"sample{extension}"
        data = _sample(extension)
        response = await client.post(
            f"/api/v1/jobs/{job_id}/input",
            files={"file": (filename, data, content_type)},
            headers=headers,
        )
        assert response.status_code == 201, f"{filename}: {response.text}"
        uploaded.append((filename, extension, content_type, data))

    assert len(uploaded) == 46

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)
        status = await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))

    assert status == "completed"
    artifact = json.loads(storage.resolve(result.artifact_path).read_text())
    entries = artifact["inspected_files"]
    assert {entry["original_filename"] for entry in entries} == {
        f"sample{e}" for e in ALLOWED_UPLOAD_TYPES
    }

    for filename, extension, _content_type, _data in uploaded:
        entry = next(e for e in entries if e["original_filename"] == filename)
        assert entry["supported_for_inspection"] is True, filename
        assert entry["media_category"] == EXTENSION_CATEGORIES[extension], filename
        if extension in _METADATA_ONLY_FORMATS:
            assert entry["extracted_chars"] is None, filename
        else:
            assert entry["extracted_chars"] and entry["extracted_chars"] > 0, filename