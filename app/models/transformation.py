import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.blueprint import Blueprint
    from app.models.deliverable import Deliverable
    from app.models.transformation_output_format import TransformationOutputFormat
    from app.models.transformation_source import TransformationSource
    from app.models.user import User

TRANSFORMATION_STATUS_TRANSITIONS: frozenset[str] = frozenset(
    {"draft", "planned", "generating", "completed", "failed"}
)


class Transformation(Base):
    """Top-level container that groups sources, output formats, blueprints
    and deliverables under a single user-owned workflow.
    """

    __tablename__ = "transformations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'planned', 'generating', 'completed', 'failed')",
            name="ck_transformations_status",
        ),
        {"comment": "User-owned transformation workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="transformations")
    sources: Mapped[list["TransformationSource"]] = relationship(
        "TransformationSource",
        back_populates="transformation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TransformationSource.created_at",
    )
    output_formats: Mapped[list["TransformationOutputFormat"]] = relationship(
        "TransformationOutputFormat",
        back_populates="transformation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    blueprints: Mapped[list["Blueprint"]] = relationship(
        "Blueprint",
        back_populates="transformation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Blueprint.version",
    )
    deliverables: Mapped[list["Deliverable"]] = relationship(
        "Deliverable",
        back_populates="transformation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Deliverable.revision",
    )
