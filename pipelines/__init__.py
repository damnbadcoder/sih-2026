"""
SIH PS 26154 Multimodal Intelligence Pipelines Package.

Modalities:
- text_pipeline: Documents (PDF, DOCX, MD, TXT, LOG, CSV, JSON), IOC extraction, table parsing, LLM Minto grounding
- image_pipeline: Visual forensics, threat diagrams, semantic visual grounding, Gemini Vision interpretation
- video_pipeline: Incident briefing videos, terminal screencast keyframe sampling, Whisper audio split, scene triage
- audio_pipeline: Incident triage calls, podcast wiretaps, temporal and speaker grounding, Gemini Audio interpretation
"""

from pipelines.base import BasePipeline

# Image Pipeline Exports
from pipelines.image_pipeline import (
    ImagePipeline,
    ingest_image,
    ImageExtractor,
    process_image_pipeline,
    PipelineResult as ImagePipelineResult,
    GroundingAnchor as ImageGroundingAnchor,
    ImageProvenance,
)

# Audio Pipeline Exports
from pipelines.audio_pipeline import (
    AudioPipeline,
    ingest_audio,
    AudioExtractor,
    process_audio_pipeline,
    AudioPipelineResult,
    AudioGroundingAnchor,
    AudioProvenance,
)

# Text Pipeline Exports
from pipelines.text_pipeline.schema import (
    ExtractedSourceContext,
    DocumentMetadata,
    ExtractedIOCs,
    TableData,
    ThreatIntelSummary,
    LLMInjectionBundle,
    SemanticChunk,
    EnrichedGroundingContext,
    ThreatMetadata,
    MintoPyramidAnalysis,
    DownstreamDirectives,
)
from pipelines.text_pipeline.ingest import (
    TextIngestionPipeline,
    TextPipeline,
    ingest_text,
)

# Video Pipeline Exports
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
from pipelines.video_pipeline.ingest import (
    VideoIngestionPipeline,
    VideoPipeline,
    ingest_video,
)


def __getattr__(name: str):
    if name in ("Interpreter", "GroqInterpreter", "QwenGroqInterpreter"):
        from pipelines.text_pipeline.interpreters.interpreter import GroqInterpreter
        return GroqInterpreter
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Base
    "BasePipeline",
    # Text
    "TextPipeline",
    "TextIngestionPipeline",
    "ingest_text",
    "ExtractedSourceContext",
    "EnrichedGroundingContext",
    "ThreatMetadata",
    "MintoPyramidAnalysis",
    "DownstreamDirectives",
    "DocumentMetadata",
    "ExtractedIOCs",
    "TableData",
    "ThreatIntelSummary",
    "LLMInjectionBundle",
    "SemanticChunk",
    # Image
    "ImagePipeline",
    "ingest_image",
    "ImageExtractor",
    "process_image_pipeline",
    "ImagePipelineResult",
    "ImageGroundingAnchor",
    "ImageProvenance",
    # Audio
    "AudioPipeline",
    "ingest_audio",
    "AudioExtractor",
    "process_audio_pipeline",
    "AudioPipelineResult",
    "AudioGroundingAnchor",
    "AudioProvenance",
    # Video
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
