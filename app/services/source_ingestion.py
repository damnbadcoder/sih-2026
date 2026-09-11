"""Source ingestion boundary for the transformation domain.

A transformation may attach three kinds of first-class sources:

- ``file``: a previously uploaded :class:`InputFile` (owned through ``Job``).
- ``text``: raw inline text persisted on the source row.
- ``url``: an external URL that is **never fetched**.  Ingestion records a
  deterministic policy decision (:mod:`app.core.url_policy`) in
  ``source_metadata.fetch_policy``; a future durable fetcher must re-evaluate
  that policy seam before any network access.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.url_policy import evaluate_url
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.transformation import Transformation
from app.models.transformation_source import TransformationSource
from app.models.user import User
from app.schemas.transformation import SourceCreate
from app.services.errors import OwnershipError, SourceAttachError


class SourceIngestionService:
    """Persists the source inputs of one transformation."""

    async def attach_sources(
        self,
        db: AsyncSession,
        transformation: Transformation,
        sources: list[SourceCreate],
        user: User,
    ) -> list[TransformationSource]:
        attached: list[TransformationSource] = []
        for source in sources:
            attached.append(
                await self._attach_one(db, transformation, source, user)
            )
        return attached

    async def _attach_one(
        self,
        db: AsyncSession,
        transformation: Transformation,
        source: SourceCreate,
        user: User,
    ) -> TransformationSource:
        if source.source_type == "file":
            if source.input_file_id is None:
                raise SourceAttachError("file sources require input_file_id")
            return await self._attach_file(db, transformation, source)
        if source.source_type == "text":
            return TransformationSource(
                source_type="text",
                text_content=source.text,
                label=source.label,
            )
        return self._attach_url(transformation, source)

    async def _attach_file(
        self,
        db: AsyncSession,
        transformation: Transformation,
        source: SourceCreate,
    ) -> TransformationSource:
        if source.input_file_id is None:
            raise SourceAttachError("file sources require input_file_id")
        stored = await db.scalar(
            select(InputFile)
            .join(Job, Job.id == InputFile.job_id)
            .where(
                InputFile.id == source.input_file_id,
                Job.user_id == transformation.user_id,
            )
        )
        if stored is None:
            raise OwnershipError(
                "input file does not exist or does not belong to the owner"
            )
        return TransformationSource(
            source_type="file",
            input_file_id=stored.id,
            label=source.label,
            source_metadata={
                "original_filename": stored.original_filename,
                "content_type": stored.content_type,
                "file_size_bytes": stored.file_size,
            },
        )

    def _attach_url(
        self, transformation: Transformation, source: SourceCreate
    ) -> TransformationSource:
        if source.url is None:
            raise SourceAttachError("url sources require a url")
        decision = evaluate_url(source.url)
        source_metadata: dict = {
            "fetch_policy": {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "host": decision.host,
            },
            "fetched": False,
        }
        return TransformationSource(
            source_type="url",
            url=source.url,
            label=source.label,
            source_metadata=source_metadata,
        )


__all__ = ["SourceIngestionService", "SourceAttachError"]