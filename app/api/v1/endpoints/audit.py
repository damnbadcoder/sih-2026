import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


def compute_entry_hash(
    job_id: uuid.UUID,
    event_type: str,
    event_data: dict | str,
    previous_hash: str,
    timestamp: datetime,
) -> str:
    if isinstance(event_data, dict):
        serialized_data = json.dumps(event_data, sort_keys=True)
    else:
        serialized_data = str(event_data)

    unique_seed = uuid.uuid4().hex
    raw_payload = f"{job_id}:{event_type}:{serialized_data}:{previous_hash}:{timestamp.isoformat()}:{unique_seed}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


async def append_audit_event(
    db: AsyncSession,
    job_id: uuid.UUID,
    event_type: str,
    event_data: dict,
) -> AuditLog:
    last_log = await db.scalar(
        select(AuditLog)
        .where(AuditLog.job_id == job_id)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )

    previous_hash = last_log.entry_hash if last_log else GENESIS_HASH
    created_at = datetime.now(UTC)

    if isinstance(event_data, dict):
        serialized_data = json.dumps(event_data, sort_keys=True)
    else:
        serialized_data = str(event_data)

    entry_hash = compute_entry_hash(
        job_id=job_id,
        event_type=event_type,
        event_data=event_data,
        previous_hash=previous_hash,
        timestamp=created_at,
    )

    audit_log = AuditLog(
        job_id=job_id,
        event_type=event_type,
        event_data=serialized_data,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    return audit_log


async def verify_audit_chain(db: AsyncSession, job_id: uuid.UUID) -> bool:
    result = await db.scalars(
        select(AuditLog)
        .where(AuditLog.job_id == job_id)
        .order_by(AuditLog.created_at.asc())
    )
    logs = list(result)

    expected_previous = GENESIS_HASH
    for log in logs:
        if log.previous_hash != expected_previous:
            return False
        expected_previous = log.entry_hash

    return True

# app/api/v1/endpoints/audit.py

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventResponse

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


async def get_db():
    async with async_session_factory() as session:
        yield session


@router.get("/{tenant_id}", response_model=list[AuditEventResponse])
async def get_audit_trail(
    tenant_id: UUID,
    event_type: Optional[str] = Query(None),
    actor_user_id: Optional[UUID] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if actor_user_id:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)

    query = query.order_by(desc(AuditEvent.created_at)).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    return events