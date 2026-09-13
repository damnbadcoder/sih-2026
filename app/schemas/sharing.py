# app/schemas/sharing.py

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ShareLinkCreate(BaseModel):
    permission: str = Field(default="read", pattern="^(read|write)$")
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(default=None, ge=1)
    requires_auth: bool = Field(default=False)
    recipient_email: Optional[str] = None


class ShareLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    token: str
    transformation_id: UUID
    created_by: UUID
    permission: str
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = None
    use_count: int
    requires_auth: bool
    recipient_email: Optional[str] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime