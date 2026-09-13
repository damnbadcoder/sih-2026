# tests/test_audit.py

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.db.session import async_session_factory, engine
from app.db.base import Base
from app.models.job import Job
from app.models.user import User
from app.models.audit import AuditEvent
from app.models.audit_log import AuditLog
from app.services.audit import AuditLogger
from app.processing.audit import append_audit_event, verify_audit_chain


@pytest.fixture(autouse=True, scope="module")
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_audit_chain_integrity():
    async with async_session_factory() as db:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=f"audit_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="fakehash",
        )
        db.add(user)
        await db.commit()

        job = Job(id=uuid.uuid4(), user_id=user_id, status="created")
        db.add(job)
        await db.commit()

        await append_audit_event(db, job.id, "JOB_CREATED", {"status": "created"})
        await append_audit_event(db, job.id, "FILE_UPLOADED", {"filename": "evidence.pdf"})

        assert await verify_audit_chain(db, job.id) is True

        log = await db.scalar(
            select(AuditLog)
            .where(AuditLog.job_id == job.id)
            .order_by(AuditLog.created_at.asc())
            .limit(1)
        )
        log.event_data = '{"status": "tampered_data"}'
        await db.commit()

        assert await verify_audit_chain(db, job.id) is False


def test_compute_hash():
    h1 = AuditLogger.compute_hash("cybersecurity data")
    h2 = AuditLogger.compute_hash("cybersecurity data")
    h3 = AuditLogger.compute_hash("tampered data")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_audit_logger_service():
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    file_hash = AuditLogger.compute_hash("sample input payload")

    async with async_session_factory() as db:
        event = await AuditLogger.log_event(
            db=db,
            event_type="input_received",
            actor_user_id=actor_id,
            tenant_id=tenant_id,
            target_type="input_file",
            target_id=target_id,
            target_hash=file_hash,
            metadata={"filename": "threat_report.pdf", "size_bytes": 2304},
        )
        assert event.id is not None
        assert event.event_type == "input_received"
        assert event.target_hash == file_hash


@pytest.mark.asyncio
async def test_get_audit_trail_endpoint():
    tenant_id = uuid.uuid4()
    async with async_session_factory() as db:
        await AuditLogger.log_event(
            db=db,
            event_type="deliverable_signed",
            tenant_id=tenant_id,
            target_type="deliverable",
            target_hash=AuditLogger.compute_hash("signed advisory payload"),
            metadata={"tlp": "amber"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/audit/{tenant_id}?event_type=deliverable_signed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["event_type"] == "deliverable_signed"
        assert data[0]["tenant_id"] == str(tenant_id)
        assert data[0]["event_metadata"]["tlp"] == "amber"