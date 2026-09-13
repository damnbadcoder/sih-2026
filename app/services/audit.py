# app/services/audit.py

import hashlib
from typing import Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditEvent


class AuditLogger:
    @staticmethod
    def compute_hash(data: bytes | str) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    async def log_event(
        db: AsyncSession,
        event_type: str,
        actor_user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        target_type: Optional[str] = None,
        target_id: Optional[UUID] = None,
        target_hash: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            target_type=target_type or "system",
            target_id=target_id,
            target_hash=target_hash,
            event_metadata=metadata or {},
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event