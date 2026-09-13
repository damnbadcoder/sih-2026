import json
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import app.processing.inspection.registry as inspection_registry
from app.core.formats import (
    MEDIA_CATEGORY_AUDIO,
    MEDIA_CATEGORY_DOCUMENT,
    MEDIA_CATEGORY_IMAGE,
    MEDIA_CATEGORY_PRESENTATION,
    MEDIA_CATEGORY_TEXT,
    MEDIA_CATEGORY_UNKNOWN,
    MEDIA_CATEGORY_VIDEO,
    FormatClass,
    classify_format,
)
from app.db.session import async_session_factory
from app.main import app
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing.inspection import (
    AudioInspector,
    InspectionError,
    InspectionResult,
    TextInspector,
    get_inspector,
    register_inspector,
)
from app.processing.service import ProcessingError, process_job, reserve_job_for_processing
from app.storage import get_storage
from app.storage.local import LocalStorage

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


async def _bytes_chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


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


def make_input_file(
    storage: LocalStorage,
    filename: str,
    content_type: str,
    data: bytes,
    storage_path: str | None = None,
) -> InputFile:
    path = storage_path or f"{uuid.uuid4()}/job/{filename}"
    return InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename=filename,
        stored_filename=f"stored_{filename}",
        content_type=content_type,
        file_size=len(data),
        storage_path=path,
    )


async def write_via_storage(storage: LocalStorage, input_file: InputFile, data: bytes) -> None:
    await storage.save(
        _bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1
    )


# --- format classification -------------------------------------------------


def test_classify_core_upload_types():
    pptx = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert classify_format("notes.txt", "text/plain").media_category == MEDIA_CATEGORY_TEXT
    assert classify_format("paper.pdf", "application/pdf").media_category == MEDIA_CATEGORY_DOCUMENT
    assert classify_format("slides.pptx", pptx).media_category == MEDIA_CATEGORY_PRESENTATION
    assert classify_format("article.docx", docx).media_category == MEDIA_CATEGORY_DOCUMENT


def test_classify_media_categories():
    assert classify_format("photo.png", "image/png").media_category == MEDIA_CATEGORY_IMAGE
    assert classify_format("clip.mp4", "video/mp4").media_category == MEDIA_CATEGORY_VIDEO
    assert classify_format("song.mp3", "audio/mpeg").media_category == MEDIA_CATEGORY_AUDIO


def test_classify_unknown_extension():
    result = classify_format("mystery.xyz", "application/octet-stream")
    assert result.media_category == MEDIA_CATEGORY_UNKNOWN
    assert result.extension == ".xyz"
    assert result.mime_type == "application/octet-stream"


def test_classify_mime_fallback_when_no_extension():
    result = classify_format("report", "image/png")
    assert result.media_category == MEDIA_CATEGORY_IMAGE
    assert result.extension is None


def test_classify_mime_parameters_ignored():
    result = classify_format("notes.txt", "text/plain; charset=utf-8")
    assert result.media_category == MEDIA_CATEGORY_TEXT
    assert result.mime_type == "text/plain"


def test_classify_contradictory_extension_and_mime_is_unknown():
    result = classify_format("paper.pdf", "image/png")
    assert result.media_category == MEDIA_CATEGORY_UNKNOWN


def test_classify_normalizes_case_and_paths():
    assert (
        classify_format(r"C:\Users\Jatin\Notes.TXT", "text/plain").media_category
        == MEDIA_CATEGORY_TEXT
    )
    assert (
        classify_format("/tmp/REPORT.PDF", "application/pdf").media_category
        == MEDIA_CATEGORY_DOCUMENT
    )


def test_classify_returns_format_class():
    result = classify_format("notes.txt", "text/plain")
    assert isinstance(result, FormatClass)
    assert result.media_category == MEDIA_CATEGORY_TEXT


# --- inspector selection ----------------------------------------------------


def test_inspector_selection_returns_text_and_none_for_others():
    assert isinstance(get_inspector(MEDIA_CATEGORY_TEXT), TextInspector)
    assert isinstance(get_inspector(MEDIA_CATEGORY_AUDIO), AudioInspector)
    assert get_inspector(MEDIA_CATEGORY_DOCUMENT) is None
    assert get_inspector(MEDIA_CATEGORY_PRESENTATION) is None
    assert get_inspector(MEDIA_CATEGORY_IMAGE) is None
    assert get_inspector(MEDIA_CATEGORY_VIDEO) is None
    assert get_inspector(MEDIA_CATEGORY_UNKNOWN) is None


async def test_register_inspector_makes_category_supported():
    class _DummyInspector:
        media_category = MEDIA_CATEGORY_IMAGE

        async def inspect(self, file, storage) -> InspectionResult:
            raise AssertionError("should not be called")

    register_inspector(_DummyInspector())
    try:
        assert get_inspector(MEDIA_CATEGORY_IMAGE) is not None
    finally:
        inspection_registry._INSPECTORS.pop(MEDIA_CATEGORY_IMAGE, None)


# --- TEXT inspection --------------------------------------------------------


async def test_text_inspection_extracts_utf8(storage: LocalStorage):
    data = "hello wörld ✓".encode()
    input_file = make_input_file(storage, "notes.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_TEXT
    assert result.original_filename == "notes.txt"
    assert result.content_type == "text/plain"
    assert result.file_size == len(data)
    assert result.extension == ".txt"
    assert result.extracted_text == "hello wörld ✓"


async def test_text_inspection_strips_utf8_bom(storage: LocalStorage):
    data = b"\xef\xbb\xbfhello"
    input_file = make_input_file(storage, "bom.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    assert result.extracted_text == "hello"
    assert result.metadata["char_count"] == 5


async def test_text_inspection_invalid_utf8_is_graceful(storage: LocalStorage):
    data = b"ok\xff\xfebytes"
    input_file = make_input_file(storage, "bad.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.extracted_text is not None
    assert "\ufffd" in result.extracted_text


async def test_text_inspection_empty_file(storage: LocalStorage):
    data = b""
    input_file = make_input_file(storage, "empty.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.extracted_text == ""
    assert result.metadata["char_count"] == 0


async def test_text_inspection_respects_size_limit(storage: LocalStorage):
    data = b"a" * 100
    input_file = make_input_file(storage, "big.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector(max_text_bytes=10).inspect(input_file, storage)

    assert result.extracted_text == "a" * 10
    assert result.metadata["truncated"] is True
    assert result.metadata["char_count"] == 10


async def test_text_inspection_missing_file_raises(storage: LocalStorage):
    input_file = make_input_file(storage, "ghost.txt", "text/plain", b"x")

    with pytest.raises(InspectionError):
        await TextInspector().inspect(input_file, storage)


async def test_text_inspection_size_mismatch_raises(storage: LocalStorage):
    input_file = make_input_file(storage, "fake.txt", "text/plain", b"x" * 10)
    await write_via_storage(storage, input_file, b"different length")

    with pytest.raises(InspectionError):
        await TextInspector().inspect(input_file, storage)


# --- storage abstraction & path hygiene -------------------------------------


class _RecordingStorage(LocalStorage):
    def __init__(self, base_dir) -> None:
        super().__init__(base_dir)
        self.read_calls: list[str] = []

    async def read_chunks(self, storage_path, *, chunk_size):
        self.read_calls.append(storage_path)
        async for chunk in super().read_chunks(storage_path, chunk_size=chunk_size):
            yield chunk


async def test_inspection_goes_through_storage_abstraction(storage: LocalStorage):
    store = _RecordingStorage(storage._base_dir)
    data = b"through storage"
    input_file = make_input_file(storage, "notes.txt", "text/plain", data)
    await write_via_storage(store, input_file, data)
    store.read_calls.clear()

    result = await TextInspector().inspect(input_file, store)

    assert store.read_calls == [input_file.storage_path]
    assert result.extracted_text == "through storage"


async def test_inspection_result_has_no_absolute_paths(storage: LocalStorage):
    data = b"path hygiene"
    input_file = make_input_file(storage, "report.txt", "text/plain", data)
    await write_via_storage(storage, input_file, data)

    result = await TextInspector().inspect(input_file, storage)

    clean_fields = {k: v for k, v in result.__dict__.items() if k != "content_type"}
    serialized = json.dumps(clean_fields, default=str)
    assert str(storage._base_dir) not in serialized
    assert "/" not in serialized
    assert "\\" not in serialized
    assert "storage_path" not in result.__dict__
    assert result.original_filename == "report.txt"
    assert result.metadata == {"truncated": False, "char_count": 12}


def test_unsupported_result_is_application_level():
    classification = classify_format(
        "slides.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    input_file = InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename="slides.pptx",
        stored_filename="stored_slides.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        file_size=0,
        storage_path="unused/path",
    )
    result = InspectionResult.unsupported(input_file, classification)

    assert result.supported_for_inspection is False
    assert result.media_category == MEDIA_CATEGORY_PRESENTATION
    assert result.extracted_text is None
    assert "reason" in result.metadata


# --- processing-service integration -----------------------------------------


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
    client: AsyncClient,
    token: str,
    job_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> None:
    if content_type is None:
        content_type = "text/plain" if filename.endswith("txt") else "application/pdf"
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _job_status(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def _reserve_and_process(job_id: str, storage: LocalStorage):
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        return await process_job(uuid.UUID(job_id), db, storage)


async def _read_artifact(storage: LocalStorage, artifact_path: str) -> dict:
    return json.loads(storage.resolve(artifact_path).read_text())


async def test_processing_calls_inspection_for_text(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("insp_txt")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "notes.txt", b"inspection text")

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    artifact = await _read_artifact(storage, result.artifact_path)
    assert artifact["inspected_files"] == [
        {
            "original_filename": "notes.txt",
            "media_category": MEDIA_CATEGORY_TEXT,
            "supported_for_inspection": True,
            "extracted_chars": 15,
            "metadata": {"truncated": False, "char_count": 15},
        }
    ]


async def test_processing_unsupported_presentation_completes_but_flagged(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("insp_pptx")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(
        client,
        token,
        job_id,
        "slides.pptx",
        b"%PPTX fake bytes",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    artifact = await _read_artifact(storage, result.artifact_path)
    assert artifact["inspected_files"] == [
        {
            "original_filename": "slides.pptx",
            "media_category": MEDIA_CATEGORY_PRESENTATION,
            "supported_for_inspection": False,
            "extracted_chars": None,
            "metadata": {"reason": "no inspector registered for media category"},
        }
    ]


async def test_processing_stored_file_verification_failure_fails_job(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("insp_mismatch")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "notes.txt", b"original bytes")

    async with async_session_factory() as db:
        input_file = await db.scalar(
            select(InputFile).where(InputFile.job_id == uuid.UUID(job_id))
        )
        assert input_file is not None
    await storage.save(
        _bytes_chunks(b"shorter"), input_file.storage_path, max_size=20
    )

    with pytest.raises(ProcessingError):
        await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "failed"