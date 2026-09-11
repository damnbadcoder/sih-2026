import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.session import async_session_factory
from app.main import app
from app.models.artifact import Artifact
from app.models.user import User
from app.storage import get_storage
from app.storage.local import LocalStorage

CREATED_EMAILS: list[str] = []


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


INPUT_FILE_FIELDS = {"id", "job_id", "original_filename", "content_type", "file_size", "created_at"}
ARTIFACT_FIELDS = {"id", "job_id", "artifact_type", "file_path", "created_at"}


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


async def _create_job(client: AsyncClient, token: str, config: dict | None = None) -> str:
    resp = await client.post(
        "/api/v1/jobs", json={"config": config}, headers=_auth(token)
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(client: AsyncClient, token: str, job_id: str, filename: str) -> None:
    content_type = "text/plain" if filename.endswith("txt") else "application/pdf"
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, b"file bytes", content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _insert_artifacts(job_id: str, user_id: str, artifact_types: list[str]) -> None:
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        for i, artifact_type in enumerate(artifact_types):
            artifact = Artifact(
                job_id=uuid.UUID(job_id),
                artifact_type=artifact_type,
                file_path=f"{user_id}/{job_id}/artifacts/{artifact_type}.out",
                created_at=now - timedelta(minutes=len(artifact_types) - i),
            )
            db.add(artifact)
        await db.commit()


async def test_get_job_unauthenticated(client: AsyncClient):
    response = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == 401


async def test_owner_retrieves_job_with_empty_relationships(client: AsyncClient):
    email = unique_email("read_empty")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token, config={"tone": "formal"})

    response = await client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "id",
        "status",
        "config",
        "created_at",
        "updated_at",
        "input_files",
        "artifacts",
    }
    assert data["id"] == job_id
    assert data["status"] == "created"
    assert data["config"] == {"tone": "formal"}
    assert data["created_at"]
    assert data["updated_at"]
    assert data["input_files"] == []
    assert data["artifacts"] == []


async def test_other_user_cannot_retrieve_job(client: AsyncClient):
    email1 = unique_email("read_owner")
    email2 = unique_email("read_other")
    CREATED_EMAILS.extend([email1, email2])
    _, token1 = await _signup_and_login(client, email1)
    _, token2 = await _signup_and_login(client, email2)
    job_id = await _create_job(client, token1)

    response = await client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token2))
    assert response.status_code == 404


async def test_get_nonexistent_job_is_404(client: AsyncClient):
    email = unique_email("read_missing")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await client.get(f"/api/v1/jobs/{uuid.uuid4()}", headers=_auth(token))
    assert response.status_code == 404


async def test_get_job_invalid_uuid_is_422(client: AsyncClient):
    email = unique_email("read_badid")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await client.get("/api/v1/jobs/not-a-uuid", headers=_auth(token))
    assert response.status_code == 422


async def test_get_job_returns_full_details_with_input_files_and_artifacts(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("read_full")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token, config={"sections": 3})

    await _upload(client, token, job_id, "notes.txt")
    await _upload(client, token, job_id, "report.pdf")
    await _insert_artifacts(job_id, user_id, ["pptx", "pdf"])

    response = await client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["config"] == {"sections": 3}

    input_files = data["input_files"]
    assert len(input_files) == 2
    assert input_files == sorted(input_files, key=lambda f: f["created_at"])
    for item in input_files:
        assert set(item) == INPUT_FILE_FIELDS
        assert item["job_id"] == job_id
    assert {f["original_filename"] for f in input_files} == {"notes.txt", "report.pdf"}
    assert {f["content_type"] for f in input_files} == {"text/plain", "application/pdf"}

    artifacts = data["artifacts"]
    assert len(artifacts) == 2
    assert artifacts == sorted(artifacts, key=lambda a: a["created_at"])
    assert [a["artifact_type"] for a in artifacts] == ["pptx", "pdf"]
    for item in artifacts:
        assert set(item) == ARTIFACT_FIELDS
        assert item["job_id"] == job_id
        assert item["file_path"].startswith("/") is False
        assert item["file_path"].startswith(str(storage._base_dir)) is False


async def test_get_job_response_leaks_no_internal_state(
    client: AsyncClient, storage: LocalStorage
):
    email = unique_email("read_leak")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "notes.txt")
    await _insert_artifacts(job_id, user_id, ["pdf"])

    response = await client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token))
    assert response.status_code == 200
    body = response.text

    assert "password_hash" not in body
    assert "user_id" not in body
    assert "email" not in body
    assert "stored_filename" not in body
    assert "storage_path" not in body
    assert "UPLOAD_DIR" not in body
    assert "upload root" not in body
    assert str(storage._base_dir) not in body

    input_files = response.json()["input_files"]
    for item in input_files:
        assert set(item) == INPUT_FILE_FIELDS