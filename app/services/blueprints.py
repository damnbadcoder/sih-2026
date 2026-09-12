"""Versioned blueprint service.

Every blueprint edit creates a **new persisted version**; previous content is
never overwritten.  Only the newest version of a ``(transformation,
output_format)`` pair is marked current.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.output_formats import is_output_format
from app.models.blueprint import Blueprint
from app.models.user import User
from app.services.errors import NotFoundError, OutputFormatError
from app.services.transformations import TransformationService


class BlueprintService:
    """Ownership-scoped blueprint versioning."""

    def __init__(self, transformations: TransformationService | None = None) -> None:
        self._transformations = transformations or TransformationService()

    async def create_version(
        self,
        db: AsyncSession,
        user: User,
        transformation_id: uuid.UUID,
        output_format: str,
        content: str,
        *,
        approve: bool = False,
    ) -> Blueprint:
        if not is_output_format(output_format):
            raise OutputFormatError(
                f"'{output_format}' is not one of the nine supported output formats"
            )
        transformation = await self._transformations.get_for_user(
            db, user, transformation_id
        )
        if not content or not content.strip():
            raise ValueError("blueprint content must not be empty")

        current_max = await db.scalar(
            select(func.max(Blueprint.version)).where(
                Blueprint.transformation_id == transformation.id,
                Blueprint.output_format == output_format,
            )
        )
        version = (current_max or 0) + 1

        await db.execute(
            update(Blueprint)
            .where(
                Blueprint.transformation_id == transformation.id,
                Blueprint.output_format == output_format,
            )
            .values(is_current=False)
        )
        blueprint = Blueprint(
            transformation_id=transformation.id,
            output_format=output_format,
            version=version,
            content=content,
            is_current=True,
            approved_at=datetime.now(UTC) if approve else None,
        )
        db.add(blueprint)
        await db.commit()
        await db.refresh(blueprint)
        return blueprint

    async def list_versions(
        self,
        db: AsyncSession,
        user: User,
        transformation_id: uuid.UUID,
        output_format: str,
    ) -> list[Blueprint]:
        if not is_output_format(output_format):
            raise OutputFormatError(
                f"'{output_format}' is not one of the nine supported output formats"
            )
        transformation = await self._transformations.get_for_user(
            db, user, transformation_id
        )
        rows = await db.scalars(
            select(Blueprint)
            .where(
                Blueprint.transformation_id == transformation.id,
                Blueprint.output_format == output_format,
            )
            .order_by(Blueprint.version)
        )
        return list(rows)

    async def ensure_owned(
        self, db: AsyncSession, user: User, blueprint: Blueprint
    ) -> Blueprint:
        await self._transformations.get_for_user(db, user, blueprint.transformation_id)
        return blueprint


__all__ = ["BlueprintService", "NotFoundError", "OutputFormatError"]