"""
Backward-compatible re-exports for schema models.
"""
from .schema import (
    ImageProvenance,
    GroundingAnchor,
    EntitiesDetected,
    PipelineResult,
)

__all__ = [
    "ImageProvenance",
    "GroundingAnchor",
    "EntitiesDetected",
    "PipelineResult",
]
