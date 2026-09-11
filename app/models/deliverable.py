import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.transformation import Transformation


class Deliverable(Base):
    """Immutable revision of a generated output for one output format.

    Every generation or refinement creates a **new persisted revision** and
    marks prior revisions non-current.  A revision must never be overwritten
    in place.
    """

    __tablename__ = "deliverables"
    __table_args__ = (
        UniqueConstraint(
            "transformation_id",
            "output_format",
            "revision",
            name="uq_deliverables_transformation_format_revision",
        ),
        CheckConstraint("revision >= 1", name="ck_deliverables_revision"),
        {"comment": "Generated deliverable revision for one output format"},
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
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    transformation: Mapped["Transformation"] = relationship(
        "Transformation",
        back_populates="deliverables",
    )
