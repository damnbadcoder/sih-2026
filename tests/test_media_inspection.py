import io
import json
import struct
import uuid
import zipfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.formats import (
    MEDIA_CATEGORY_AUDIO,
    MEDIA_CATEGORY_DOCUMENT,
    MEDIA_CATEGORY_IMAGE,
    MEDIA_CATEGORY_TEXT,
    MEDIA_CATEGORY_VIDEO,
)
from app.core.uploads import ALLOWED_UPLOAD_TYPES
from app.db.session import async_session_factory
from app.main import app
from app.models.artifact import Artifact
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing.inspection import (
    AudioInspector,
    ImageInspector,
    InspectionError,
    TextInspector,
    VideoInspector,
    XLSXInspector,
)
from app.processing.normalization import iter_normalized_records
from app.processing.service import (
    ProcessingError,
    process_job,
    reserve_job_for_processing,
)
from app.storage import get_storage
from app.storage.local import LocalStorage

_PNG_MIME = "image/png"
_JPEG_MIME = "image/jpeg"
_MP3_MIME = "audio/mpeg"
_MP4_MIME = "video/mp4"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MD_MIME = "text/markdown"

CREATED_EMAILS: list[str] = []


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


# --- minimal, spec-valid format builders --------------------------------------


def build_xlsx_text() -> bytes:
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


def build_png(width: int = 640, height: int = 480) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", 0)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"") + chunk(b"IEND", b"")


def build_jpeg(width: int = 640, height: int = 480) -> bytes:
    app0 = struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", height, width) + b"\x03"
    return b"\xff\xd8\xff\xe0" + app0 + b"\xff\xc0" + sof0 + b"\xff\xd9"


def _syncsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def build_mp3(title: str = "Nocturne", tail_bytes: int = 4096) -> bytes:
    encoded = title.encode("latin-1")
    payload = b"\x00" + encoded  # encoding byte 0 = latin-1
    frame = b"TIT2" + struct.pack(">I", len(payload)) + b"\x00\x00" + payload
    id3 = b"ID3\x03\x00\x00" + _syncsafe(len(frame)) + frame
    # 0xFFFB9000 = MPEG1, Layer III, 128 kbps, 44100 Hz, stereo.
    return id3 + struct.pack(">I", 0xFFFB9000) + b"\x00" * tail_bytes


def _box(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + tag + payload


def build_mp4(duration_ms: int = 3000, handler: bytes = b"vide") -> bytes:
    mvhd = _box(
        b"mvhd",
        b"\x00\x00\x00\x00" + struct.pack(">I", 0) + struct.pack(">I", 0)
        + struct.pack(">I", 1000) + struct.pack(">I", duration_ms),
    )
    tkhd = _box(
        b"tkhd",
        b"\x00\x00\x00\x00" + struct.pack(">I", 0) + struct.pack(">I", 0)
        + struct.pack(">I", 1) + struct.pack(">I", 0) + struct.pack(">I", duration_ms)
        + b"\x00\x00\x00\x00\x00\x00\x00\x00" + struct.pack(">H", 0) + struct.pack(">H", 0)
        + struct.pack(">H", 0x0100) + struct.pack(">H", 0) + b"\x00" * 36
        + struct.pack(">II", 640 << 16, 480 << 16),
    )
    hdlr = _box(b"hdlr", b"\x00\x00\x00\x00\x00\x00\x00\x00" + handler + b"\x00" * 12)
    mdia = _box(b"mdia", hdlr)
    trak = _box(b"trak", tkhd + mdia)
    return _box(b"ftyp", b"isom\x00\x00\x00\x00isomiso2") + _box(b"moov", mvhd + trak)


async def _bytes_chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


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


async def write_via_storage(storage: LocalStorage, input_file: InputFile, data: bytes) -> None:
    await storage.save(_bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    user_id = signup.json()["id"]
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


async def _create_job(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/v1/jobs", json={"config": {}}, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(
    client: AsyncClient, token: str, job_id: str, filename: str, content: bytes
) -> None:
    content_type = ALLOWED_UPLOAD_TYPES["." + filename.rsplit(".", 1)[1]]
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text


async def _job_status(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def _artifact_count(job_id: str) -> int:
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.job_id == uuid.UUID(job_id))
        )


async def _reserve_and_process(job_id: str, storage: LocalStorage):
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        return await process_job(uuid.UUID(job_id), db, storage)


async def _read_artifact(storage: LocalStorage, artifact_path: str) -> dict:
    return json.loads(storage.resolve(artifact_path).read_text())


# --- inspector unit tests ------------------------------------------------------


async def test_xlsx_inspection_extracts_cells(storage: LocalStorage):
    data = build_xlsx_text()
    input_file = make_input_file("data.xlsx", _XLSX_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await XLSXInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_DOCUMENT
    assert result.extracted_text == "Alpha\t7"
    assert result.metadata == {
        "format": "xlsx",
        "sheet_count": 1,
        "row_count": 1,
        "cell_count": 2,
        "char_count": 7,
        "truncated": False,
    }


async def test_xlsx_inspection_malformed_raises_inspection_error(storage: LocalStorage):
    data = b"this is not a zip"
    input_file = make_input_file("broken.xlsx", _XLSX_MIME, data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await XLSXInspector().inspect(input_file, storage)


async def test_markdown_inspection_uses_text_inspector(storage: LocalStorage):
    data = b"# Heading\n\nSome **bold** text.\n"
    input_file = make_input_file("README.md", _MD_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_TEXT
    assert result.extension == ".md"
    assert result.extracted_text == data.decode()
    assert result.metadata == {"truncated": False, "char_count": len(data)}


@pytest.mark.parametrize(
    ("builder", "filename", "expect"),
    [
        (lambda: build_png(320, 200), "photo.png", {"format": "png", "width": 320, "height": 200}),
        (
            lambda: build_jpeg(800, 600),
            "photo.jpg",
            {"format": "jpeg", "width": 800, "height": 600},
        ),
    ],
)
async def test_image_inspection_extracts_dimensions(
    storage: LocalStorage, builder, filename, expect
):
    data = builder()
    mime = _PNG_MIME if filename.endswith("png") else _JPEG_MIME
    input_file = make_input_file(filename, mime, data)
    await write_via_storage(storage, input_file, data)

    result = await ImageInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_IMAGE
    assert result.extracted_text is None
    for key, value in expect.items():
        assert result.metadata[key] == value


async def test_image_inspection_rejects_magic_extension_mismatch(storage: LocalStorage):
    data = build_jpeg(80, 80)
    input_file = make_input_file("trick.png", _PNG_MIME, data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await ImageInspector().inspect(input_file, storage)


async def test_image_inspection_rejects_garbage(storage: LocalStorage):
    data = b"this is not an image at all"
    input_file = make_input_file("junk.png", _PNG_MIME, data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await ImageInspector().inspect(input_file, storage)


async def test_audio_inspection_extracts_frame_and_id3(storage: LocalStorage):
    data = build_mp3(title="Interlude", tail_bytes=8192)
    input_file = make_input_file("track.mp3", _MP3_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await AudioInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_AUDIO
    assert result.extracted_text is None
    assert result.metadata["format"] == "mp3"
    assert result.metadata["version"] == "MPEG1"
    assert result.metadata["layer"] == "Layer III"
    assert result.metadata["bitrate_kbps"] == 128
    assert result.metadata["sample_rate_hz"] == 44100
    assert result.metadata["channels"] == 2
    assert result.metadata["title"] == "Interlude"
    assert result.metadata["duration_estimate_seconds"] > 0


async def test_audio_inspection_rejects_non_mp3(storage: LocalStorage):
    data = b"\x00\x00\x00\x00 this is not mp3 audio"
    input_file = make_input_file("fake.mp3", _MP3_MIME, data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await AudioInspector().inspect(input_file, storage)


async def test_video_inspection_extracts_boxes(storage: LocalStorage):
    data = build_mp4(duration_ms=500, handler=b"vide")
    input_file = make_input_file("clip.mp4", _MP4_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await VideoInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_VIDEO
    assert result.extracted_text is None
    assert result.metadata["brand"] == "isom"
    assert result.metadata["duration_seconds"] == pytest.approx(0.5)
    assert result.metadata["has_video"] is True
    assert result.metadata["has_audio"] is False
    assert result.metadata["width"] == 640
    assert result.metadata["height"] == 480


async def test_video_inspection_rejects_non_mp4(storage: LocalStorage):
    payload = b"\x00\x00\x00\x00garbage not mp4"
    input_file = make_input_file("fake.mp4", _MP4_MIME, payload)
    await write_via_storage(storage, input_file, payload)

    with pytest.raises(InspectionError):
        await VideoInspector().inspect(input_file, storage)


async def test_media_inspection_leaves_no_grounding_gap(storage: LocalStorage):
    """Media inspectors are supported (never flagged unsupported) and their
    records reach Stage 13 with an explicit 'no extractable text' reason,
    so the Stage 14 grounding seam is exposed rather than silently lost."""
    png = make_input_file("a.png", _PNG_MIME, build_png())
    mp3 = make_input_file("b.mp3", _MP3_MIME, build_mp3())
    mp4 = make_input_file("c.mp4", _MP4_MIME, build_mp4())
    for f, data in ((png, build_png()), (mp3, build_mp3()), (mp4, build_mp4())):
        await write_via_storage(storage, f, data)

    records = []
    for f in (png, mp3, mp4):
        if f is png:
            result = await ImageInspector().inspect(f, storage)
        elif f is mp3:
            result = await AudioInspector().inspect(f, storage)
        else:
            result = await VideoInspector().inspect(f, storage)
        records.append(next(iter_normalized_records([result])))

    for record in records:
        assert record["supported_for_inspection"] is True
        assert record["normalized_text"] is None
        assert record["reason"] == "no extractable text"


# --- processing-service integration for the required formats -------------------


@pytest.mark.parametrize(
    ("filename", "builder"),
    [
        ("photo.png", build_png),
        ("photo.jpg", build_jpeg),
        ("track.mp3", build_mp3),
        ("clip.mp4", build_mp4),
        ("sheet.xlsx", build_xlsx_text),
        ("README.md", lambda: b"# Note\n\nGrounding for media is deferred.\n"),
    ],
)
async def test_each_new_required_format_processes_with_single_artifact(
    client: AsyncClient, storage: LocalStorage, filename, builder
):
    email = unique_email("fmt")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, filename, builder())

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    assert await _artifact_count(job_id) == 1
    artifact = await _read_artifact(storage, result.artifact_path)
    entry = artifact["inspected_files"][0]
    assert entry["original_filename"] == filename
    assert entry["supported_for_inspection"] is True
    if filename.endswith((".png", ".jpg", ".mp3", ".mp4")):
        assert entry["extracted_chars"] is None
    else:
        assert entry["extracted_chars"] > 0


async def test_mixed_format_job_produces_single_artifact(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("fmt_mixed")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    for filename, builder in [
        ("notes.txt", lambda: b"plain text\n"),
        ("photo.png", build_png),
        ("clip.mp4", build_mp4),
        ("sheet.xlsx", build_xlsx_text),
    ]:
        await _upload(client, token, job_id, filename, builder())

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    assert await _artifact_count(job_id) == 1
    artifact = await _read_artifact(storage, result.artifact_path)
    entries = artifact["inspected_files"]
    assert {entry["original_filename"] for entry in entries} == {
        "notes.txt",
        "photo.png",
        "clip.mp4",
        "sheet.xlsx",
    }
    assert {entry["media_category"] for entry in entries} == {
        MEDIA_CATEGORY_TEXT,
        MEDIA_CATEGORY_IMAGE,
        MEDIA_CATEGORY_VIDEO,
        MEDIA_CATEGORY_DOCUMENT,
    }
    assert all(entry["supported_for_inspection"] is True for entry in entries)


@pytest.mark.parametrize(
    ("filename", "bad_bytes"),
    [
        ("fake.png", b"not a png, just text"),
        ("fake.mp3", b"also not audio"),
        ("fake.mp4", b"definitely not an mp4 box stream"),
        ("fake.xlsx", b"not a zip archive"),
    ],
)
async def test_malformed_media_fails_processing(
    client: AsyncClient, storage: LocalStorage, filename, bad_bytes
):
    email = unique_email("fmt_bad")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, filename, bad_bytes)

    with pytest.raises(ProcessingError):
        await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "failed"