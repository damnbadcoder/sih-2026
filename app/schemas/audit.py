# app/schemas/audit.py

from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    id: UUID
    event_type: str
    actor_user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    target_type: str
    target_id: Optional[UUID] = None
    target_hash: Optional[str] = None
    event_metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="event_metadata")
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True