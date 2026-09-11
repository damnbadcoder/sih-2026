"""Immutable deliverable revision service.

Every generation or refinement creates a **new persisted revision**; previous
content is never overwritten.  Only the newest revision of a ``(transformation,
output_format)`` pair is marked current.
"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.output_formats import is_output_format
from app.models.deliverable import Deliverable
from app.models.user import User
from app.services.errors import NotFoundError, OutputFormatError
from app.services.transformations import TransformationService


class DeliverableService:
    """Ownership-scoped deliverable revisioning."""

    def __init__(self, transformations: TransformationService | None = None) -> None:
        self._transformations = transformations or TransformationService()

    async def create_revision(
        self,
        db: AsyncSession,
        user: User,
        transformation_id: uuid.UUID,
        output_format: str,
        content: str,
        generation_metadata: dict[str, Any] | None = None,
    ) -> Deliverable:
        if not is_output_format(output_format):
            raise OutputFormatError(
                f"'{output_format}' is not one of the nine supported output formats"
            )
        transformation = await self._transformations.get_for_user(
            db, user, transformation_id
        )
        if not content or not content.strip():
            raise ValueError("deliverable content must not be empty")

        current_max = await db.scalar(
            select(func.max(Deliverable.revision)).where(
                Deliverable.transformation_id == transformation.id,
                Deliverable.output_format == output_format,
            )
        )
        revision = (current_max or 0) + 1

        await db.execute(
            update(Deliverable)
            .where(
                Deliverable.transformation_id == transformation.id,
                Deliverable.output_format == output_format,
            )
            .values(is_current=False)
        )
        deliverable = Deliverable(
            transformation_id=transformation.id,
            output_format=output_format,
            revision=revision,
            content=content,
            is_current=True,
            generation_metadata=generation_metadata,
        )
        db.add(deliverable)
        await db.commit()
        await db.refresh(deliverable)
        return deliverable

    async def list_revisions(
        self,
        db: AsyncSession,
        user: User,
        transformation_id: uuid.UUID,
        output_format: str,
    ) -> list[Deliverable]:
        if not is_output_format(output_format):
            raise OutputFormatError(
                f"'{output_format}' is not one of the nine supported output formats"
            )
        transformation = await self._transformations.get_for_user(
            db, user, transformation_id
        )
        rows = await db.scalars(
            select(Deliverable)
            .where(
                Deliverable.transformation_id == transformation.id,
                Deliverable.output_format == output_format,
            )
            .order_by(Deliverable.revision)
        )
        return list(rows)


__all__ = ["DeliverableService", "NotFoundError", "OutputFormatError"]