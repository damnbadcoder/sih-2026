import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.input_file import InputFile
    from app.models.transformation import Transformation


class TransformationSource(Base):
    """An ingestible source attached to a transformation.

    Exactly one of ``input_file_id``, ``text_content``, or ``url`` will be
    populated depending on ``source_type``.  The product guarantees that
    external URLs are never fetched: the ``source_metadata`` JSON records a
    deterministic ``fetch_policy`` decision made at ingestion time.  A future
    durable fetcher must re-evaluate the same policy seam rather than blindly
    following the persisted decision.
    """

    __tablename__ = "transformation_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('file', 'text', 'url')",
            name="ck_transformation_sources_source_type",
        ),
        Index("ix_transformation_sources_input_file", "input_file_id"),
        {"comment": "Ingestible source attached to a transformation workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transformation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transformations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    input_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("input_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    transformation: Mapped["Transformation"] = relationship(
        "Transformation",
        back_populates="sources",
    )
    input_file: Mapped["InputFile | None"] = relationship(
        "InputFile",
        lazy="select",
    )

    @property
    def has_text(self) -> bool:
        return bool(self.text_content)

    @property
    def text_length(self) -> int:
        return len(self.text_content) if self.text_content else 0
