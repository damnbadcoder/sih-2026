import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.main import app
from app.db.session import async_session_factory
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.services.correlation import CorrelationEngine
from app.storage.local import LocalStorage

CREATED_EMAILS: list[str] = []


async def cleanup_created_users() -> None:
    if not CREATED_EMAILS:
        return
    async with async_session_factory() as db:
        await db.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))
        await db.commit()
    CREATED_EMAILS.clear()


def test_correlation_engine_scoring_and_structure():
    payload = {
        "iocs": [
            {"value": "10.0.0.1", "type": "ip", "source": "evtx"},
            {"value": "10.0.0.1", "type": "ip", "source": "pdf"},
            {"value": "bad_hash", "type": "hash", "source": "evtx"},
        ]
    }
    engine = CorrelationEngine()
    result = engine.build_graph(payload)

    assert "nodes" in result
    assert "links" in result
    assert len(result["nodes"]) == 2

    ip_node = next(n for n in result["nodes"] if n["id"] == "10.0.0.1")
    assert ip_node["source_count"] == 2
    assert ip_node["is_novel"] is True
    assert ip_node["cross_source_confidence"] == 0.7


@pytest.mark.asyncio
async def test_get_correlations_endpoint_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        fake_id = uuid.uuid4()
        response = await ac.get(f"/api/v1/transformations/{fake_id}/correlations")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_correlations_endpoint_success(monkeypatch, tmp_path):
    email = f"corr-{uuid.uuid4().hex[:8]}@example.com"
    CREATED_EMAILS.append(email)

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(LocalStorage, "__init__", lambda self, base_dir=None: super(LocalStorage, self).__init__())
    monkeypatch.setattr(LocalStorage, "resolve", lambda self, p: upload_dir / p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        signup = await ac.post("/api/v1/auth/signup", json={"email": email, "password": "password123"})
        assert signup.status_code == 201
        user_id = signup.json()["id"]

        login = await ac.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        async with async_session_factory() as db:
            job = Job(user_id=uuid.UUID(user_id), status="completed")
            db.add(job)
            await db.commit()
            await db.refresh(job)

            payload = {
                "iocs": [
                    {"value": "172.16.0.5", "type": "ip", "source": "pcap"},
                    {"value": "cve-2026-1234", "type": "cve", "source": "pcap"},
                ]
            }

            rel_path = f"artifacts/{job.id}/result.json"
            file_data = json.dumps(payload).encode("utf-8")

            artifact_file = upload_dir / rel_path
            artifact_file.parent.mkdir(parents=True, exist_ok=True)
            artifact_file.write_bytes(file_data)

            artifact = Artifact(
                job_id=job.id,
                artifact_type="processing_result",
                file_path=rel_path,
            )
            db.add(artifact)
            await db.commit()
            job_id_str = str(job.id)

        response = await ac.get(
            f"/api/v1/transformations/{job_id_str}/correlations",
            headers=auth_headers,
        )
        if response.status_code != 200:
            print("SERVER ERROR RESPONSE:", response.text)

    await cleanup_created_users()

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id_str
    assert "correlation_graph" in data
    assert len(data["correlation_graph"]["nodes"]) == 2