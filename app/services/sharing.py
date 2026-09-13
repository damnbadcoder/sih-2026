# app/services/sharing.py

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_link import ShareLink
from app.models.transformation import Transformation
from app.services.audit import AuditLogger


class SharingService:
    @staticmethod
    async def create_share_link(
        db: AsyncSession,
        transformation_id: UUID,
        user_id: UUID,
        tenant_id: Optional[UUID],
        permission: str = "read",
        expires_at: Optional[datetime] = None,
        max_uses: Optional[int] = None,
        requires_auth: bool = False,
        recipient_email: Optional[str] = None,
    ) -> ShareLink:
        trans_res = await db.execute(select(Transformation).where(Transformation.id == transformation_id))
        transformation = trans_res.scalar_one_or_none()
        if not transformation:
            raise ValueError("Transformation not found.")

        tlp = getattr(transformation, "tlp", "green").lower()
        if tlp == "red":
            raise ValueError("TLP:RED transformations cannot be shared via public or external links.")

        if tlp == "amber" and not requires_auth:
            requires_auth = True

        token = secrets.token_urlsafe(32)
        share_link = ShareLink(
            token=token,
            transformation_id=transformation_id,
            created_by=user_id,
            permission=permission,
            expires_at=expires_at,
            max_uses=max_uses,
            requires_auth=requires_auth,
            recipient_email=recipient_email,
        )
        db.add(share_link)
        await db.commit()
        await db.refresh(share_link)

        await AuditLogger.log_event(
            db=db,
            event_type="share_link_created",
            actor_user_id=user_id,
            tenant_id=tenant_id,
            target_type="share_link",
            target_id=share_link.id,
            target_hash=AuditLogger.compute_hash(token),
            metadata={"permission": permission, "requires_auth": requires_auth},
        )

        return share_link

    @staticmethod
    async def resolve_share_link(
        db: AsyncSession,
        token: str,
        user_email: Optional[str] = None,
    ) -> ShareLink:
        res = await db.execute(select(ShareLink).where(ShareLink.token == token))
        link = res.scalar_one_or_none()

        if not link or link.revoked_at is not None:
            raise ValueError("Share link is invalid or has been revoked.")

        now = datetime.now(timezone.utc)
        if link.expires_at and link.expires_at < now:
            raise ValueError("Share link has expired.")

        if link.max_uses and link.use_count >= link.max_uses:
            raise ValueError("Share link usage limit has been reached.")

        if link.recipient_email and link.recipient_email != user_email:
            raise ValueError("Email mismatch for restricted share link.")

        link.use_count += 1
        await db.commit()
        await db.refresh(link)
        return link

    @staticmethod
    async def revoke_link(db: AsyncSession, link_id: UUID, user_id: UUID) -> bool:
        res = await db.execute(select(ShareLink).where(ShareLink.id == link_id))
        link = res.scalar_one_or_none()
        if not link or link.created_by != user_id:
            return False

        link.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        return True