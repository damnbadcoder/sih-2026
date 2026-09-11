import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.main import app
from app.models.transformation import Transformation
from app.models.transformation_output_format import TransformationOutputFormat
from app.models.transformation_source import TransformationSource
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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    email = unique_email("stage14transform")
    CREATED_EMAILS.append(email)
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return login.json()["user"], login.json()["access_token"]


def _create_payload(sources: list[dict] | None = None) -> dict:
    return {
        "title": "SolarWinds response",
        "outputs": [
            {
                "outputType": "exec_summary",
                "parameters": {
                    "audienceCategory": "executive",
                    "tone": "Executive & Concise",
                    "detail": "Comprehensive Analysis",
                    "objective": "Executive Risk Assessment",
                    "language": "English",
                },
            },
            {"outputType": "incident_report"},
        ],
        "sources": sources or [{"source_type": "text", "text": "CVE-2026-0001 observed."}],
    }


async def test_create_transformation_persists_sources_formats_and_params(client: AsyncClient):
    user, token = await _register_and_login(client)

    response = await client.post(
        "/api/v1/transformations",
        json=_create_payload(),
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "draft"

    formats = {item["output_format"] for item in data["outputs"]}
    assert formats == {"exec_summary", "incident_report"}

    async with async_session_factory() as db:
        transformation = await db.scalar(
            select(Transformation).where(Transformation.id == uuid.UUID(data["id"]))
        )
        assert transformation is not None
        assert transformation.user_id == uuid.UUID(user["id"])
        assert transformation.status == "draft"

        params = await db.scalar(
            select(TransformationOutputFormat).where(
                TransformationOutputFormat.transformation_id == transformation.id,
                TransformationOutputFormat.output_format == "exec_summary",
            )
        )
        assert params is not None
        assert params.parameters["audience_category"] == "executive"
        assert params.parameters["objective"] == "Executive Risk Assessment"

        source = await db.scalar(
            select(TransformationSource).where(
                TransformationSource.transformation_id == transformation.id
            )
        )
        assert source is not None
        assert source.source_type == "text"
        assert source.text_content == "CVE-2026-0001 observed."


async def test_response_never_leaks_raw_text(client: AsyncClient):
    user, token = await _register_and_login(client)
    secret = "THIS-IS-SECRET-RAW-TEXT-CONTENT"
    response = await client.post(
        "/api/v1/transformations",
        json=_create_payload(sources=[{"source_type": "text", "text": secret}]),
        headers=_auth(token),
    )
    assert response.status_code == 201
    body = response.text
    assert secret not in body
    assert "text_content" not in body
    assert "THIS-IS-SECRET" not in body

    listing = await client.get("/api/v1/transformations", headers=_auth(token))
    assert secret not in listing.text


async def test_get_rejects_another_users_transformation(client: AsyncClient):
    _user_a, token_a = await _register_and_login(client)
    _user_b, token_b = await _register_and_login(client)

    created = await client.post(
        "/api/v1/transformations", json=_create_payload(), headers=_auth(token_a)
    )
    transformation_id = created.json()["id"]

    own = await client.get(
        f"/api/v1/transformations/{transformation_id}", headers=_auth(token_a)
    )
    assert own.status_code == 200

    other = await client.get(
        f"/api/v1/transformations/{transformation_id}", headers=_auth(token_b)
    )
    assert other.status_code == 404

    listing_b = await client.get("/api/v1/transformations", headers=_auth(token_b))
    assert listing_b.json() == []


async def test_create_rejects_duplicate_output_formats(client: AsyncClient):
    _user, token = await _register_and_login(client)
    payload = _create_payload()
    payload["outputs"].append({"outputType": "exec_summary"})
    response = await client.post(
        "/api/v1/transformations", json=payload, headers=_auth(token)
    )
    assert response.status_code == 422


async def test_create_rejects_unknown_output_format(client: AsyncClient):
    _user, token = await _register_and_login(client)
    payload = _create_payload()
    payload["outputs"] = [{"outputType": "mystery_notebook"}]
    response = await client.post(
        "/api/v1/transformations", json=payload, headers=_auth(token)
    )
    assert response.status_code == 422


async def test_url_source_is_persisted_never_fetched(client: AsyncClient):
    user, token = await _register_and_login(client)
    response = await client.post(
        "/api/v1/transformations",
        json=_create_payload(
            sources=[{"source_type": "url", "url": "https://example.com/feed.xml"}]
        ),
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text

    async with async_session_factory() as db:
        source = await db.scalar(
            select(TransformationSource)
            .where(TransformationSource.transformation_id == uuid.UUID(response.json()["id"]))
        )
        assert source is not None
        assert source.source_type == "url"
        assert source.url == "https://example.com/feed.xml"
        assert source.text_content is None
        assert source.input_file_id is None
        policy = source.source_metadata["fetch_policy"]
        assert policy["allowed"] is False
        assert policy["reason"]
        assert source.source_metadata["fetched"] is False


async def test_text_source_shortcut_detection_for_empty(client: AsyncClient):
    _user, token = await _register_and_login(client)
    response = await client.post(
        "/api/v1/transformations",
        json=_create_payload(sources=[{"source_type": "text", "text": "   "}]),
        headers=_auth(token),
    )
    assert response.status_code == 422


async def test_file_source_requires_belonging_input_file(client: AsyncClient):
    _user, token = await _register_and_login(client)
    foreign_file_id = uuid.uuid4()
    payload = _create_payload(
        sources=[{"source_type": "file", "input_file_id": str(foreign_file_id)}]
    )
    response = await client.post(
        "/api/v1/transformations", json=payload, headers=_auth(token)
    )
    assert response.status_code == 422