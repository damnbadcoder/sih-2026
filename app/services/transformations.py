"""Transformation workflow service.

A transformation is the user-owned container that groups sources, selected
output formats, blueprints and deliverables.  It exists independently of the
legacy :class:`Job` flow; nothing is crammed into ``Job.config``.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.transformation import Transformation
from app.models.transformation_output_format import TransformationOutputFormat
from app.models.transformation_source import TransformationSource
from app.models.user import User
from app.schemas.transformation import TransformationCreateRequest
from app.services.errors import NotFoundError, OwnershipError
from app.services.source_ingestion import SourceIngestionService

_LOAD_OPTIONS = (
    selectinload(Transformation.sources).selectinload(TransformationSource.input_file),
    selectinload(Transformation.output_formats),
)


class TransformationService:
    """Ownership-scoped operations over transformations."""

    def __init__(self, source_ingestion: SourceIngestionService | None = None) -> None:
        self._source_ingestion = source_ingestion or SourceIngestionService()

    async def create_transformation(
        self,
        db: AsyncSession,
        user: User,
        payload: TransformationCreateRequest,
    ) -> Transformation:
        transformation = Transformation(
            user_id=user.id,
            title=payload.title,
            status="draft",
        )
        transformation.output_formats = [
            TransformationOutputFormat(
                output_format=selection.output_format.value,
                parameters=selection.parameters.storage_dump(),
            )
            for selection in payload.outputs
        ]
        transformation.sources = await self._source_ingestion.attach_sources(
            db, transformation, payload.sources, user
        )
        db.add(transformation)
        await db.commit()
        return await self._load_owned(db, user, transformation.id)

    async def list_for_user(self, db: AsyncSession, user: User) -> list[Transformation]:
        rows = await db.scalars(
            select(Transformation)
            .where(Transformation.user_id == user.id)
            .options(*_LOAD_OPTIONS)
            .order_by(Transformation.created_at.desc())
        )
        return list(rows)

    async def get_for_user(
        self, db: AsyncSession, user: User, transformation_id: uuid.UUID
    ) -> Transformation:
        return await self._load_owned(db, user, transformation_id)

    async def _load_owned(
        self,
        db: AsyncSession,
        user: User,
        transformation_id: uuid.UUID,
    ) -> Transformation:
        transformation = await db.scalar(
            select(Transformation)
            .where(
                Transformation.id == transformation_id,
                Transformation.user_id == user.id,
            )
            .options(*_LOAD_OPTIONS)
        )
        if transformation is None:
            raise NotFoundError("transformation does not exist")
        return transformation


__all__ = ["TransformationService", "NotFoundError", "OwnershipError"]