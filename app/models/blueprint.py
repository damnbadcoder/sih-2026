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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.transformation import Transformation


class Blueprint(Base):
    """Versioned architectural specification for one output format.

    Every edit creates a **new persisted version** and marks prior versions
    non-current.  A version must never be overwritten in place.
    """

    __tablename__ = "blueprints"
    __table_args__ = (
        UniqueConstraint(
            "transformation_id",
            "output_format",
            "version",
            name="uq_blueprints_transformation_format_version",
        ),
        CheckConstraint("version >= 1", name="ck_blueprints_version"),
        {"comment": "Versioned blueprint for one output format"},
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
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    transformation: Mapped["Transformation"] = relationship(
        "Transformation",
        back_populates="blueprints",
    )
