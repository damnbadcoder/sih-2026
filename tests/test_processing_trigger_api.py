import asyncio
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.db.session import async_session_factory
from app.main import app
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.processing import runner
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
def storage(tmp_path, monkeypatch) -> LocalStorage:
    store = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: store
    monkeypatch.setattr(runner, "get_storage", lambda: store)
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


async def _upload(client: AsyncClient, token: str, job_id: str) -> None:
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": ("notes.txt", b"uploaded content", "text/plain")},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _setup(client: AsyncClient, email: str) -> tuple[str, str]:
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id)
    return token, job_id


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


async def _trigger(client: AsyncClient, token: str, job_id: str):
    return await client.post(f"/api/v1/jobs/{job_id}/process", headers=_auth(token))


async def _wait_for_status(
    client: AsyncClient, token: str, job_id: str, wanted: str, timeout: float = 5.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] == wanted:
            return data
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach status {wanted!r}")


async def test_process_unauthenticated(client: AsyncClient):
    response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/process")
    assert response.status_code == 401


async def test_process_nonexistent_job_returns_404(client: AsyncClient):
    email = unique_email("trig_missing")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await _trigger(client, token, str(uuid.uuid4()))
    assert response.status_code == 404


async def test_foreign_user_cannot_process_job(client: AsyncClient):
    email1 = unique_email("trig_owner")
    email2 = unique_email("trig_other")
    CREATED_EMAILS.extend([email1, email2])
    _, token1 = await _signup_and_login(client, email1)
    _, token2 = await _signup_and_login(client, email2)
    job_id = await _create_job(client, token1)

    response = await _trigger(client, token2, job_id)
    assert response.status_code == 404


async def test_process_invalid_uuid_returns_422(client: AsyncClient):
    email = unique_email("trig_badid")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await client.post("/api/v1/jobs/not-a-uuid/process", headers=_auth(token))
    assert response.status_code == 422


async def test_trigger_accepts_processing_and_completes_job(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("trig_ok")
    token, job_id = await _setup(client, email)

    response = await _trigger(client, token, job_id)
    assert response.status_code == 202
    assert response.json() == {"job_id": str(job_id), "status": "processing"}

    data = await _wait_for_status(client, token, job_id, "completed")
    assert data["status"] == "completed"
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["artifact_type"] == "processing_result"
    assert await _artifact_count(job_id) == 1


async def test_trigger_response_leaks_no_internal_state(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("trig_leak")
    token, job_id = await _setup(client, email)

    response = await _trigger(client, token, job_id)
    assert response.status_code == 202
    body = response.text
    assert "storage_path" not in body
    assert "user_id" not in body
    assert "email" not in body
    assert str(storage._base_dir) not in body
    assert set(response.json()) == {"job_id", "status"}
    await _wait_for_status(client, token, job_id, "completed")


class _GateStorage(LocalStorage):
    """Blocks writes to the artifacts directory until released."""

    def __init__(self, base_dir) -> None:
        super().__init__(base_dir)
        self.release = asyncio.Event()
        self.save_entered = asyncio.Event()

    async def save(self, chunks, storage_path: str, *, max_size: int) -> int:
        if "/artifacts/" in storage_path:
            self.save_entered.set()
            await self.release.wait()
        return await super().save(chunks, storage_path, max_size=max_size)


class _FailingSaveStorage(LocalStorage):
    async def save(self, chunks, storage_path: str, *, max_size: int) -> int:
        raise StorageError("simulated artifact write failure")


async def test_trigger_returns_before_processing_finishes(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("trig_fast")
    token, job_id = await _setup(client, email)

    gate = _GateStorage(storage._base_dir)
    monkeypatch.setattr(runner, "get_storage", lambda: gate)

    response = await _trigger(client, token, job_id)
    assert response.status_code == 202
    assert await _job_status(job_id) == "processing"

    deadline = time.monotonic() + 5.0
    while not gate.save_entered.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert gate.save_entered.is_set(), "runner never reached the artifact write"

    gate.release.set()
    await _wait_for_status(client, token, job_id, "completed")
    assert await _artifact_count(job_id) == 1


async def test_duplicate_trigger_while_processing_returns_409(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("trig_dup")
    token, job_id = await _setup(client, email)

    gate = _GateStorage(storage._base_dir)
    monkeypatch.setattr(runner, "get_storage", lambda: gate)

    first = await _trigger(client, token, job_id)
    assert first.status_code == 202
    assert await _job_status(job_id) == "processing"

    second = await _trigger(client, token, job_id)
    assert second.status_code == 409

    gate.release.set()
    await _wait_for_status(client, token, job_id, "completed")
    assert await _artifact_count(job_id) == 1


async def test_trigger_already_completed_job_returns_409(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("trig_done")
    token, job_id = await _setup(client, email)

    first = await _trigger(client, token, job_id)
    assert first.status_code == 202
    await _wait_for_status(client, token, job_id, "completed")

    second = await _trigger(client, token, job_id)
    assert second.status_code == 409


async def test_trigger_failed_job_returns_409(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("trig_failonce")
    token, job_id = await _setup(client, email)

    failing = _FailingSaveStorage(storage._base_dir)
    monkeypatch.setattr(runner, "get_storage", lambda: failing)

    first = await _trigger(client, token, job_id)
    assert first.status_code == 202
    await _wait_for_status(client, token, job_id, "failed")
    assert await _artifact_count(job_id) == 0

    second = await _trigger(client, token, job_id)
    assert second.status_code == 409


async def test_processing_failure_transitions_job_to_failed(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("trig_fail")
    token, job_id = await _setup(client, email)

    failing = _FailingSaveStorage(storage._base_dir)
    monkeypatch.setattr(runner, "get_storage", lambda: failing)

    response = await _trigger(client, token, job_id)
    assert response.status_code == 202
    await _wait_for_status(client, token, job_id, "failed")
    assert await _artifact_count(job_id) == 0


async def test_runner_uses_its_own_session_factory(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    email = unique_email("trig_ownsf")
    token, job_id = await _setup(client, email)

    original = runner.async_session_factory
    calls = [0]

    def counting_factory(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "async_session_factory", counting_factory)

    response = await _trigger(client, token, job_id)
    assert response.status_code == 202
    await _wait_for_status(client, token, job_id, "completed")
    assert calls[0] >= 1