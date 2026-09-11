import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.transformation import Transformation


class TransformationOutputFormat(Base):
    """Selected output format for a transformation, together with its
    per-format generation parameters.

    The product decision is to persist parameter snapshots so that a future
    generation run can reconstruct exactly what was chosen at the time.
    """

    __tablename__ = "transformation_output_formats"
    __table_args__ = (
        UniqueConstraint(
            "transformation_id",
            "output_format",
            name="uq_transformation_output_formats_transformation_format",
        ),
        {"comment": "Output format selection with generation parameter snapshot"},
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
    output_format: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    transformation: Mapped["Transformation"] = relationship(
        "Transformation",
        back_populates="output_formats",
    )
