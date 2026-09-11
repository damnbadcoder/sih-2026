import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GroundedSource(BaseModel):
    """Normalized source content plus extracted indicators, ready for
    blueprint/deliverable generation and hallucination validation."""

    source_id: uuid.UUID
    source_type: str
    label: str | None = None
    media_category: str | None = None
    normalized_text: str | None = None
    truncated: bool = False
    reason: str | None = None
    iocs: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundingContext(BaseModel):
    """Aggregated grounding result for one transformation.

    ``indicators`` is the union of indicators extracted across all sources,
    keyed by canonical IOC type (cve, ipv4, ipv6, sha256, domain, url, etc.).
    """

    transformation_id: uuid.UUID
    sources: list[GroundedSource]
    indicators: dict[str, list[str]]
    ioc_extraction_available: bool
    generated_at: datetime