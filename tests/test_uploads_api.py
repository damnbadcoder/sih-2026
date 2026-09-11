import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.uploads import ALLOWED_UPLOAD_TYPES
from app.db.session import async_session_factory, engine
from app.main import app
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.storage import get_storage
from app.storage.local import LocalStorage

_STORED_NAME_RE = re.compile(r"[0-9a-f]{32}\.(mp3|mp4|docx|xlsx|pdf|png|jpeg|jpg|txt|md)")

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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MD = "text/markdown"


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
    content_type: str,
):
    return await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )


def _stored_files(storage: LocalStorage, job_id: str) -> list:
    return [p for p in storage._base_dir.rglob(f"*/{job_id}/input/*") if p.is_file()]


async def _input_rows(job_id: str) -> int:
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count()).select_from(InputFile).where(InputFile.job_id == uuid.UUID(job_id))
        )


async def test_upload_unauthenticated(client: AsyncClient):
    response = await client.post(
        f"/api/v1/jobs/{uuid.uuid4()}/input",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401


async def test_upload_to_nonexistent_job(client: AsyncClient):
    email = unique_email("up_missing")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    response = await _upload(
        client, token, str(uuid.uuid4()), "a.txt", b"hello", "text/plain"
    )
    assert response.status_code == 404


async def test_upload_to_another_users_job_is_404(client: AsyncClient):
    email1 = unique_email("up_owner")
    email2 = unique_email("up_other")
    CREATED_EMAILS.extend([email1, email2])
    _, token1 = await _signup_and_login(client, email1)
    _, token2 = await _signup_and_login(client, email2)
    job_id = await _create_job(client, token1)

    response = await _upload(
        client, token2, job_id, "a.txt", b"hello", "text/plain"
    )
    assert response.status_code == 404
    assert await _input_rows(job_id) == 0


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("report.pdf", "application/pdf", b"%PDF-1.4\n% dummy pdf\n"),
        ("sheet.xlsx", _XLSX, b"PK\x03\x04dummy-sheet"),
        ("doc.docx", _DOCX, b"PK\x03\x04dummy-docx"),
        ("notes.txt", "text/plain", b"hello world\n"),
    ],
)
async def test_valid_uploads_succeed(
    client: AsyncClient, storage: LocalStorage, filename, content_type, content
):
    email = unique_email("up_valid")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    response = await _upload(client, token, job_id, filename, content, content_type)
    assert response.status_code == 201, response.text

    data = response.json()
    expected_keys = {"id", "job_id", "original_filename", "content_type", "file_size", "created_at"}
    assert set(data) == expected_keys
    assert data["job_id"] == job_id
    assert data["original_filename"] == filename
    assert data["content_type"] == content_type
    assert data["file_size"] == len(content)

    async with async_session_factory() as db:
        row = await db.scalar(select(InputFile).where(InputFile.id == uuid.UUID(data["id"])))
        assert row is not None
        assert row.job_id == uuid.UUID(job_id)
        assert row.original_filename == filename
        assert row.content_type == content_type
        assert row.file_size == len(content)
        assert re.fullmatch(_STORED_NAME_RE, row.stored_filename)
        assert row.stored_filename != filename
        assert row.storage_path == f"{user_id}/{job_id}/input/{row.stored_filename}"

    stored = _stored_files(storage, job_id)
    assert len(stored) == 1
    assert stored[0].read_bytes() == content
    assert stored[0].suffix == "." + filename.rsplit(".", 1)[1]


@pytest.mark.parametrize(
    "extension",
    ["mp3", "mp4", "docx", "xlsx", "pdf", "png", "jpeg", "jpg", "txt", "md"],
)
async def test_all_ten_required_formats_upload_succeed(
    client: AsyncClient, storage: LocalStorage, extension
):
    email = unique_email("up_ten")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    filename = f"sample.{extension}"
    content_type = ALLOWED_UPLOAD_TYPES[f".{extension}"]
    response = await _upload(client, token, job_id, filename, b"payload bytes", content_type)
    assert response.status_code == 201, response.text

    data = response.json()
    async with async_session_factory() as db:
        row = await db.scalar(select(InputFile).where(InputFile.id == uuid.UUID(data["id"])))
        assert row.content_type == content_type
        assert row.stored_filename.endswith(f".{extension}")
        assert row.storage_path == f"{user_id}/{job_id}/input/{row.stored_filename}"


async def test_uploaded_file_contents_match_on_disk(client: AsyncClient, storage: LocalStorage):
    email = unique_email("up_bytes")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    content = (b"line 1\nline 2\nline 3\n") * 1000
    response = await _upload(client, token, job_id, "big.txt", content, "text/plain")
    assert response.status_code == 201
    stored = _stored_files(storage, job_id)
    assert len(stored) == 1
    assert stored[0].read_bytes() == content


async def test_path_traversal_filename_cannot_escape(client: AsyncClient, storage: LocalStorage):
    email = unique_email("up_trav")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    response = await _upload(
        client, token, job_id, "../../../etc/passwd.pdf", b"%PDF", "application/pdf"
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["original_filename"] == "passwd.pdf"

    async with async_session_factory() as db:
        row = await db.scalar(select(InputFile).where(InputFile.id == uuid.UUID(data["id"])))
        assert str(row.storage_path) == f"{user_id}/{job_id}/input/{row.stored_filename}"

    for path in _stored_files(storage, job_id):
        assert str(path).startswith(str(storage._base_dir.resolve()))
        assert ".." not in path.name
    assert not (storage._base_dir.resolve().parent / "etc").exists()


def test_db_storage_paths_are_relative_not_absolute():
    from app.core.uploads import validate_upload_type

    _, ext = validate_upload_type("x.txt", "text/plain")
    joined = f"{uuid.uuid4()}/{uuid.uuid4()}/input/{uuid.uuid4().hex}{ext}"
    assert joined.startswith("/") is False
    assert ":" not in joined


async def test_stored_filename_is_server_generated(client: AsyncClient):
    email = unique_email("up_srv")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    response = await _upload(client, token, job_id, "notes.txt", b"x", "text/plain")
    assert response.status_code == 201
    async with async_session_factory() as db:
        row = await db.scalar(select(InputFile).where(InputFile.job_id == uuid.UUID(job_id)))
        assert re.fullmatch(r"[0-9a-f]{32}\.txt", row.stored_filename)
        assert row.stored_filename != "notes.txt"
        assert row.original_filename == "notes.txt"


async def test_oversized_upload_returns_413_and_leaves_no_trace(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("up_big")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_SIZE_BYTES", 10)
    response = await _upload(
        client, token, job_id, "big.txt", b"0123456789ABCDEF", "text/plain"
    )
    assert response.status_code == 413
    assert await _input_rows(job_id) == 0
    assert _stored_files(storage, job_id) == []


@pytest.mark.parametrize("filename", ["notes.pdf", "notes.docx", "notes.png"])
async def test_content_type_mismatch_rejected(client: AsyncClient, storage: LocalStorage, filename):
    email = unique_email("up_mismatch")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    response = await _upload(client, token, job_id, filename, b"x", "text/plain")
    assert response.status_code == 415
    assert await _input_rows(job_id) == 0
    assert _stored_files(storage, job_id) == []


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("run.exe", "application/octet-stream"),
        ("archive.zip", "application/zip"),
        ("script.py", "text/x-python"),
        ("icons.svg", "image/svg+xml"),
    ],
)
async def test_unsupported_type_rejected(
    client: AsyncClient, storage: LocalStorage, filename, content_type
):
    email = unique_email("up_badtype")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    response = await _upload(client, token, job_id, filename, b"data", content_type)
    assert response.status_code == 415
    assert await _input_rows(job_id) == 0
    assert _stored_files(storage, job_id) == []


class _FailingCommitSession(AsyncSession):
    async def commit(self) -> None:
        raise RuntimeError("forced commit failure")


async def _failing_db():
    async with _FailingCommitSession(bind=engine, expire_on_commit=False) as session:
        yield session


async def test_database_failure_cleans_up_stored_file(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("up_fail")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _failing_db
    try:
        response = await _upload(
            client, token, job_id, "crash.txt", b"uploaded bytes", "text/plain"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert await _input_rows(job_id) == 0
    assert _stored_files(storage, job_id) == []


async def test_job_input_files_relationship(client: AsyncClient):
    email = unique_email("up_rel")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)

    await _upload(client, token, job_id, "a.txt", b"a", "text/plain")
    await _upload(client, token, job_id, "b.pdf", b"%PDF", "application/pdf")

    data = await _upload(client, token, job_id, "c.docx", b"PK", _DOCX)
    file_id = data.json()["id"]

    async with async_session_factory() as db:
        job = await db.scalar(
            select(Job)
            .where(Job.id == uuid.UUID(job_id))
            .options(selectinload(Job.input_files))
        )
        assert len(job.input_files) == 3
        extensions = {f.stored_filename.rsplit(".", 1)[1] for f in job.input_files}
        assert extensions == {"txt", "pdf", "docx"}
        belongs = await db.scalar(
            select(InputFile)
            .where(InputFile.id == uuid.UUID(file_id))
            .options(selectinload(InputFile.job))
        )
        assert belongs.job.id == job.id