import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password
from app.db.session import async_session_factory
from app.main import app
from app.models.user import User

CREATED_EMAILS: list[str] = []


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def cleanup_created_users() -> None:
    if not CREATED_EMAILS:
        return
    from sqlalchemy import delete

    async with async_session_factory() as db:
        await db.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))
        await db.commit()
    CREATED_EMAILS.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _cleanup_created():
    yield
    await cleanup_created_users()


async def test_signup_success(client: AsyncClient):
    email = unique_email("signup")
    CREATED_EMAILS.append(email)

    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": "  " + email.upper() + "  ", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email  # normalized to lowercase
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


async def test_signup_duplicate_rejected(client: AsyncClient):
    email = unique_email("dup")
    CREATED_EMAILS.append(email)

    first = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/signup", json={"email": email.upper(), "password": "password123"}
    )
    assert second.status_code == 409


async def test_signup_rejects_short_password(client: AsyncClient):
    email = unique_email("short")
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "short"}
    )
    assert response.status_code == 422


async def test_login_success(client: AsyncClient):
    email = unique_email("login")
    CREATED_EMAILS.append(email)

    await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]


async def test_login_wrong_password_rejected(client: AsyncClient):
    email = unique_email("wrongpw")
    CREATED_EMAILS.append(email)

    await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrongpass"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


async def test_login_nonexistent_account_rejected(client: AsyncClient):
    email = unique_email("ghost")
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


async def test_login_inactive_user_rejected(client: AsyncClient):
    email = unique_email("inactive")
    CREATED_EMAILS.append(email)

    async with async_session_factory() as db:
        db.add(User(email=email, password_hash=hash_password("password123"), is_active=False))
        await db.commit()

    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 403


async def test_get_current_user_returns_user():
    email = unique_email("current")
    CREATED_EMAILS.append(email)

    async with async_session_factory() as db:
        user = User(email=email, password_hash=hash_password("password123"))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id))

    async with async_session_factory() as db:
        result = await get_current_user(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            db=db,
        )
        assert result.id == user_id
        assert result.email == email


async def test_get_current_user_rejects_invalid_token():
    async with async_session_factory() as db:
        with pytest.raises(HTTPException):
            await get_current_user(
                credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token"),
                db=db,
            )


async def test_get_current_user_rejects_inactive_user():
    email = unique_email("currentinactive")
    CREATED_EMAILS.append(email)

    async with async_session_factory() as db:
        user = User(email=email, password_hash=hash_password("password123"), is_active=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id))

    async with async_session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await get_current_user(
                credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                db=db,
            )
        assert exc.value.status_code == 401