import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import decode_access_token
from app.db.session import async_session_factory
from app.main import app
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


@pytest.fixture(autouse=True)
async def _cleanup_created():
    yield
    await cleanup_created_users()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register(client: AsyncClient, email: str, extra: dict | None = None) -> dict:
    payload = {
        "email": email,
        "password": "password123",
        "name": "Jatin Sharma",
        "user_type": "Researcher",
        "organisation": "NCIIPC",
    }
    if extra:
        payload.update(extra)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_register_persists_persona(client: AsyncClient):
    email = unique_email("persona")
    CREATED_EMAILS.append(email)

    data = await _register(client, email)
    assert data["name"] == "Jatin Sharma"
    assert data["user_type"] == "Researcher"
    assert data["organisation"] == "NCIIPC"

    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.name == "Jatin Sharma"
        assert user.user_type == "Researcher"
        assert user.organisation == "NCIIPC"


async def test_signup_alias_returns_same_persona(client: AsyncClient):
    email = unique_email("alias")
    CREATED_EMAILS.append(email)

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "password123",
            "name": "Alias User",
            "user_type": "Journalist",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alias User"
    assert data["user_type"] == "Journalist"
    assert "organisation" not in data or data["organisation"] is None


async def test_register_rejects_unknown_user_type(client: AsyncClient):
    email = unique_email("badtype")
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "user_type": "Superhero"},
    )
    assert response.status_code == 422


async def test_login_returns_persona_and_token_claim(client: AsyncClient):
    email = unique_email("loginpersona")
    CREATED_EMAILS.append(email)

    await _register(client, email)

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200
    data = login.json()
    assert data["user"]["user_type"] == "Researcher"
    assert data["user"]["organisation"] == "NCIIPC"

    payload = decode_access_token(data["access_token"])
    assert payload["user_type"] == "Researcher"
    assert payload["sub"] == data["user"]["id"]


async def test_login_without_persona_omits_claim(client: AsyncClient):
    email = unique_email("nopersona")
    CREATED_EMAILS.append(email)

    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201
    assert response.json()["user_type"] is None

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    token = login.json()["access_token"]
    assert "user_type" not in decode_access_token(token)