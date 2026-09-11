import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.main import app
from app.models.job import Job
from app.models.user import User

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
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await cleanup_created_users()


async def _signup_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123"},
    )
    assert signup.status_code == 201
    user_id = signup.json()["id"]
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


async def _fetch_job(job_id: str) -> Job:
    async with async_session_factory() as db:
        return await db.scalar(select(Job).where(Job.id == uuid.UUID(job_id)))


async def test_create_job_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/jobs", json={"config": {}})
    assert response.status_code == 401


async def test_authenticated_user_can_create_job(client: AsyncClient):
    email = unique_email("job")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)

    response = await client.post(
        "/api/v1/jobs",
        json={"config": {"tone": "formal", "sections": 3}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "created"
    assert data["config"] == {"tone": "formal", "sections": 3}
    assert data["created_at"]
    assert data["updated_at"]

    job = await _fetch_job(data["id"])
    assert job is not None
    assert job.id == uuid.UUID(data["id"])
    assert job.user_id == uuid.UUID(user_id)
    assert job.status == "created"
    assert job.config == {"tone": "formal", "sections": 3}


async def test_create_job_without_config_defaults_to_none(client: AsyncClient):
    email = unique_email("jo_default")
    CREATED_EMAILS.append(email)
    user_id, token = await _signup_and_login(client, email)

    response = await client.post(
        "/api/v1/jobs",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["config"] is None

    job = await _fetch_job(data["id"])
    assert job is not None
    assert job.config is None
    assert job.user_id == uuid.UUID(user_id)


async def test_create_job_rejects_client_supplied_user_id(client: AsyncClient):
    email = unique_email("job_forbid")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await client.post(
        "/api/v1/jobs",
        json={"user_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_create_job_response_exposes_no_internal_state(client: AsyncClient):
    email = unique_email("job_leak")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)

    response = await client.post(
        "/api/v1/jobs",
        json={"config": {"a": 1}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert set(response.json()) == {"id", "status", "config", "created_at", "updated_at"}