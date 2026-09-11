"""
Video Pipeline Package for Technical Cybersecurity & Threat Intelligence Videos.
Extracts aligned multimodal scenes combining Whisper audio transcription,
perceptual-hash deduplicated keyframes, visual triage (SLIDE, TERMINAL, DIAGRAM, OTHER),
specialized OCR/Mermaid extraction, and Groq semantic grounding.
"""

from pipelines.video_pipeline.schema import (
    VisualType,
    ExtractedVideoIOCs,
    AudioSegment,
    KeyframeInfo,
    VisualContent,
    AlignedScene,
    VideoMetadata,
    ExtractedVideoContext,
    VideoEnrichedGroundingContext,
    VideoMintoPyramid,
)
from pipelines.video_pipeline.ingest import VideoIngestionPipeline, VideoPipeline, ingest_video

__all__ = [
    "VideoPipeline",
    "VideoIngestionPipeline",
    "ingest_video",
    "VisualType",
    "ExtractedVideoIOCs",
    "AudioSegment",
    "KeyframeInfo",
    "VisualContent",
    "AlignedScene",
    "VideoMetadata",
    "ExtractedVideoContext",
    "VideoEnrichedGroundingContext",
    "VideoMintoPyramid",
]
