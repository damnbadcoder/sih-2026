"""
Backward-compatible re-exports for audio schema models.
"""
from .schema import (
    AudioProvenance,
    AudioGroundingAnchor,
    AudioEntitiesDetected,
    AudioPipelineResult,
)

__all__ = [
    "AudioProvenance",
    "AudioGroundingAnchor",
    "AudioEntitiesDetected",
    "AudioPipelineResult",
]
