import base64
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.signing import SigningService


def test_keypair_generation():
    priv, pub = SigningService.generate_keypair()
    assert priv is not None
    assert pub is not None
    assert isinstance(base64.b64decode(priv), bytes)
    assert isinstance(base64.b64decode(pub), bytes)


def test_sign_and_verify_service():
    priv, pub = SigningService.generate_keypair()
    content = b"cybersecurity threat intelligence report q3"
    sig = SigningService.sign_content(priv, content)
    assert SigningService.verify_signature(pub, content, sig) is True


def test_tampered_content_service():
    priv, pub = SigningService.generate_keypair()
    content = b"original content"
    sig = SigningService.sign_content(priv, content)
    tampered_content = b"tampered content"
    assert SigningService.verify_signature(pub, tampered_content, sig) is False


@pytest.mark.asyncio
async def test_verify_endpoint_success():
    priv, pub = SigningService.generate_keypair()
    content = "threat advisory content"
    sig = SigningService.sign_content(priv, content.encode("utf-8"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/deliverables/verify",
            json={
                "content": content,
                "signature": sig,
                "public_key": pub,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_authentic"] is True


@pytest.mark.asyncio
async def test_verify_endpoint_tampered():
    priv, pub = SigningService.generate_keypair()
    content = "original advisory content"
    sig = SigningService.sign_content(priv, content.encode("utf-8"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/deliverables/verify",
            json={
                "content": "modified advisory content",
                "signature": sig,
                "public_key": pub,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_authentic"] is False