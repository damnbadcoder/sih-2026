import json
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, engine
from app.main import app
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.processing.service import (
    InvalidTransitionError,
    JobNotFoundError,
    NoInputFilesError,
    ProcessingError,
    ensure_transition_allowed,
    process_job,
    reserve_job_for_processing,
)
from app.storage import StorageError, get_storage
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


_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
)


async def _upload(
    client: AsyncClient, token: str, job_id: str, filename: str = "notes.txt"
) -> None:
    if filename.endswith("txt"):
        content, content_type = b"uploaded content", "text/plain"
    else:
        content, content_type = _MINIMAL_PDF, "application/pdf"
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _setup(client: AsyncClient, email: str, upload_count: int = 1) -> tuple[str, str, str]:
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    for i in range(upload_count):
        await _upload(client, token, job_id, f"input_{i}.txt" if i % 2 == 0 else f"input_{i}.pdf")
    return user_id, token, job_id


async def _job_status(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def _artifact_count(job_id: str) -> int:
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count())
            .select_from(Artifact)
            .where(Artifact.job_id == uuid.UUID(job_id))
        )


def _artifact_files(storage: LocalStorage, job_id: str) -> list:
    root = storage._base_dir.resolve()
    return [p for p in root.rglob(f"*/{job_id}/artifacts/*") if p.is_file()]


class _ProbeStorage(LocalStorage):
    """Asserts the job is already in 'processing' when the artifact is written."""

    def __init__(self, base_dir, job_id: str) -> None:
        super().__init__(base_dir)
        self._job_id = uuid.UUID(job_id)

    async def save(self, chunks, storage_path: str, *, max_size: int) -> int:
        async with async_session_factory() as db:
            status = await db.scalar(select(Job.status).where(Job.id == self._job_id))
        assert status == "processing"
        return await super().save(chunks, storage_path, max_size=max_size)


class _FailingStorage(LocalStorage):
    async def save(self, chunks, storage_path: str, *, max_size: int) -> int:
        raise StorageError("simulated disk failure")


class _FailArtifactInsertSession(AsyncSession):
    """Forces the statement that flushes the new Artifact row to fail."""

    async def execute(
        self, statement, params=None, execution_options=(), bind_arguments=None, **kw
    ):
        if any(isinstance(obj, Artifact) for obj in self.new):
            await self.rollback()
            raise RuntimeError("forced artifact insert failure")
        return await super().execute(
            statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            **kw,
        )


async def test_process_nonexistent_job_raises(client: AsyncClient, storage: LocalStorage):
    async with async_session_factory() as db:
        with pytest.raises(JobNotFoundError):
            await process_job(uuid.uuid4(), db, storage)
    assert _artifact_files(storage, str(uuid.uuid4())) == []


async def test_job_with_no_input_files_fails(client: AsyncClient, storage: LocalStorage):
    email = unique_email("proc_none")
    _, token = await _signup_and_login(client, email)
    CREATED_EMAILS.append(email)
    job_id = await _create_job(client, token)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        with pytest.raises(NoInputFilesError):
            await process_job(uuid.UUID(job_id), db, storage)

    assert await _job_status(job_id) == "failed"
    assert await _artifact_count(job_id) == 0
    assert _artifact_files(storage, job_id) == []


async def test_valid_job_transitions_created_processing_completed(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_valid")
    _, _, job_id = await _setup(client, email, upload_count=2)
    assert await _job_status(job_id) == "created"

    probe = _ProbeStorage(storage._base_dir, job_id)
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, probe)

    assert result.job_id == uuid.UUID(job_id)
    assert result.status == "completed"
    assert result.input_file_count == 2
    assert await _job_status(job_id) == "completed"


async def test_successful_processing_creates_exactly_one_artifact(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_one")
    _, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)

    assert await _artifact_count(job_id) == 1
    async with async_session_factory() as db:
        artifact = await db.scalar(select(Artifact).where(Artifact.id == result.artifact_id))
    assert artifact.job_id == uuid.UUID(job_id)
    assert artifact.artifact_type == "processing_result"


async def test_artifact_file_path_is_relative(client: AsyncClient, storage: LocalStorage):
    email = unique_email("proc_path")
    user_id, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)

    assert result.artifact_path.startswith("/") is False
    assert result.artifact_path.startswith(str(storage._base_dir)) is False
    pattern = rf"{user_id}/{job_id}/artifacts/[0-9a-f]{{32}}\.json"
    assert re.fullmatch(pattern, result.artifact_path)


async def test_generated_artifact_exists_through_storage(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_exists")
    _, _, job_id = await _setup(client, email, upload_count=2)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)

    target = storage.resolve(result.artifact_path)
    assert target.is_file()
    content = json.loads(target.read_text())
    assert content["artifact_type"] == "processing_result"
    assert content["status"] == "completed"
    assert content["job_id"] == job_id
    assert content["input_file_count"] == 2
    filenames = {f["original_filename"] for f in content["input_files"]}
    assert filenames == {"input_0.txt", "input_1.pdf"}
    assert all("file_size" in f for f in content["input_files"])


async def test_artifact_metadata_has_no_absolute_paths(client: AsyncClient, storage: LocalStorage):
    email = unique_email("proc_abs")
    _, _, job_id = await _setup(client, email, upload_count=1)
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)
    content = storage.resolve(result.artifact_path).read_text()
    assert "/" not in content
    parsed = json.loads(content)
    assert parsed["input_files"] == [{"original_filename": "input_0.txt", "file_size": 16}]


async def test_processing_storage_failure_transitions_job_to_failed(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_fail")
    _, _, job_id = await _setup(client, email, upload_count=1)

    failing = _FailingStorage(storage._base_dir)
    with pytest.raises(ProcessingError):
        async with async_session_factory() as db:
            await reserve_job_for_processing(db, uuid.UUID(job_id))
            await process_job(uuid.UUID(job_id), db, failing)

    assert await _job_status(job_id) == "failed"
    assert await _artifact_count(job_id) == 0
    assert _artifact_files(storage, job_id) == []


def test_invalid_status_transitions_rejected():
    for current, target in [
        ("completed", "processing"),
        ("failed", "processing"),
        ("completed", "failed"),
        ("processing", "created"),
        ("completed", "created"),
    ]:
        with pytest.raises(InvalidTransitionError):
            ensure_transition_allowed(current, target)
    ensure_transition_allowed("created", "processing")
    ensure_transition_allowed("processing", "completed")
    ensure_transition_allowed("processing", "failed")


async def test_already_completed_job_cannot_be_processed_again(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_twice")
    _, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        await process_job(uuid.UUID(job_id), db, storage)
    assert await _job_status(job_id) == "completed"

    with pytest.raises(InvalidTransitionError):
        async with async_session_factory() as db:
            await process_job(uuid.UUID(job_id), db, storage)

    assert await _artifact_count(job_id) == 1


async def test_concurrent_processors_cannot_both_claim_a_created_job(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_race")
    _, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db_a:
        reserved = await reserve_job_for_processing(db_a, uuid.UUID(job_id))
    assert reserved.status == "processing"

    with pytest.raises(InvalidTransitionError):
        async with async_session_factory() as db_b:
            await reserve_job_for_processing(db_b, uuid.UUID(job_id))

    assert await _job_status(job_id) == "processing"


async def test_artifact_db_insert_failure_cleans_file_and_fails_job(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_orphan")
    _, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))

    async with _FailArtifactInsertSession(bind=engine, expire_on_commit=False) as db:
        with pytest.raises(ProcessingError):
            await process_job(uuid.UUID(job_id), db, storage)

    assert await _job_status(job_id) == "failed"
    assert await _artifact_count(job_id) == 0
    assert _artifact_files(storage, job_id) == []


async def test_reserve_nonexistent_job_raises(client: AsyncClient, storage: LocalStorage):
    async with async_session_factory() as db:
        with pytest.raises(JobNotFoundError):
            await reserve_job_for_processing(db, uuid.uuid4())


async def test_reserve_returns_processing_job(client: AsyncClient, storage: LocalStorage):
    email = unique_email("proc_reserve")
    _, _, job_id = await _setup(client, email, upload_count=1)
    assert await _job_status(job_id) == "created"

    async with async_session_factory() as db:
        job = await reserve_job_for_processing(db, uuid.UUID(job_id))

    assert job.id == uuid.UUID(job_id)
    assert job.status == "processing"
    assert await _job_status(job_id) == "processing"


async def test_reserve_completed_job_raises_invalid_transition(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("proc_reserve_done")
    _, _, job_id = await _setup(client, email, upload_count=1)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        await process_job(uuid.UUID(job_id), db, storage)
    assert await _job_status(job_id) == "completed"

    with pytest.raises(InvalidTransitionError):
        async with async_session_factory() as db:
            await reserve_job_for_processing(db, uuid.UUID(job_id))