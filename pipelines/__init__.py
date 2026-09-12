"""
SIH PS 26154 Multimodal Intelligence Pipelines Package.

Modalities:
- text_pipeline: Documents (PDF, DOCX, MD, TXT, LOG, CSV, JSON), IOC
  extraction, table parsing, LLM Minto grounding
- image_pipeline: Visual forensics, threat diagrams, semantic visual
  grounding, Gemini Vision interpretation
- video_pipeline: Incident briefing videos, terminal screencast keyframe
  sampling, Whisper audio split, scene triage
- audio_pipeline: Incident triage calls, podcast wiretaps, temporal and
  speaker grounding, Gemini Audio interpretation

Import behaviour:
The heavy modality subpackages (image/audio/video and the text ingestion +
interpreter stack) depend on external providers that are not part of the
backend service dependency set (Pillow, google-genai, groq, opencv, ...).
They are therefore exposed lazily; merely ``import pipelines`` (or importing
the ``pipelines.text_pipeline.schema`` / ``ioc_extractor`` / ``chunking``
modules) does not require those providers.  Importing a name tied to an
unprovisioned provider fails at the point of use with the underlying
``ImportError`` instead of failing the whole package.
"""

import importlib

from pipelines.base import BasePipeline

# Text schema types are dependency-light (pydantic + stdlib) and safe to
# import eagerly; they are the contract Stage 14 grounding reuses.
from pipelines.text_pipeline.schema import (
    DocumentMetadata,
    DownstreamDirectives,
    EnrichedGroundingContext,
    ExtractedIOCs,
    ExtractedSourceContext,
    LLMInjectionBundle,
    MintoPyramidAnalysis,
    SemanticChunk,
    TableData,
    ThreatIntelSummary,
    ThreatMetadata,
)

_IMAGE_EXPORTS: dict[str, str] = {
    "ImagePipeline": "ImagePipeline",
    "ingest_image": "ingest_image",
    "ImageExtractor": "ImageExtractor",
    "process_image_pipeline": "process_image_pipeline",
    "ImagePipelineResult": "PipelineResult",
    "ImageGroundingAnchor": "GroundingAnchor",
    "ImageProvenance": "ImageProvenance",
}

_AUDIO_EXPORTS: dict[str, str] = {
    "AudioPipeline": "AudioPipeline",
    "ingest_audio": "ingest_audio",
    "AudioExtractor": "AudioExtractor",
    "process_audio_pipeline": "process_audio_pipeline",
    "AudioPipelineResult": "AudioPipelineResult",
    "AudioGroundingAnchor": "AudioGroundingAnchor",
    "AudioProvenance": "AudioProvenance",
}

_VIDEO_EXPORTS: dict[str, str] = {
    "VideoPipeline": "VideoPipeline",
    "VideoIngestionPipeline": "VideoIngestionPipeline",
    "ingest_video": "ingest_video",
    "VisualType": "VisualType",
    "ExtractedVideoIOCs": "ExtractedVideoIOCs",
    "AudioSegment": "AudioSegment",
    "KeyframeInfo": "KeyframeInfo",
    "VisualContent": "VisualContent",
    "AlignedScene": "AlignedScene",
    "VideoMetadata": "VideoMetadata",
    "ExtractedVideoContext": "ExtractedVideoContext",
    "VideoEnrichedGroundingContext": "VideoEnrichedGroundingContext",
    "VideoMintoPyramid": "VideoMintoPyramid",
}

_TEXT_INGEST_EXPORTS: frozenset[str] = frozenset(
    {"TextPipeline", "TextIngestionPipeline", "ingest_text"}
)

_INTERPRETER_EXPORTS: frozenset[str] = frozenset(
    {"Interpreter", "GroqInterpreter", "QwenGroqInterpreter"}
)


def __getattr__(name: str):
    if name in _IMAGE_EXPORTS:
        module = importlib.import_module("pipelines.image_pipeline")
        return getattr(module, _IMAGE_EXPORTS[name])
    if name in _AUDIO_EXPORTS:
        module = importlib.import_module("pipelines.audio_pipeline")
        return getattr(module, _AUDIO_EXPORTS[name])
    if name in _VIDEO_EXPORTS:
        module = importlib.import_module("pipelines.video_pipeline")
        return getattr(module, _VIDEO_EXPORTS[name])
    if name in _TEXT_INGEST_EXPORTS or name in _INTERPRETER_EXPORTS:
        module = importlib.import_module("pipelines.text_pipeline")
        return getattr(module, name)
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
