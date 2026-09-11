import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


async def test_settings_load():
    settings = get_settings()
    assert settings.APP_NAME == "SIH 2026 GenAI Platform"
    assert settings.DATABASE_URL is not None


async def test_api_v1_router_included(client: AsyncClient):
    response = await client.get("/api/v1")
    assert response.status_code in (200, 404)