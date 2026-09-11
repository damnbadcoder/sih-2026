"""
Audio Ingestion & Temporal Grounding Pipeline for NTRO PS 26154.
Multimodal signals intelligence pipeline with speaker diarization and timecode citations.
"""
from .schema import (
    AudioPipelineResult,
    AudioGroundingAnchor,
    AudioProvenance,
    AudioEntitiesDetected,
)
from .ingest import AudioPipeline, ingest_audio
from .extractor import AudioExtractor, process_audio_pipeline
from .extractors.preprocessor import AudioPreprocessor
from .extractors.metadata_extractor import AudioMetadataExtractor
from .interpreters.interpreter import AudioVisionInterpreter
from .formatter import format_audio_to_markdown
from .mock import get_mock_audio_pipeline_result

__all__ = [
    "AudioPipeline",
    "ingest_audio",
    "AudioExtractor",
    "process_audio_pipeline",
    "AudioPipelineResult",
    "AudioGroundingAnchor",
    "AudioProvenance",
    "AudioEntitiesDetected",
    "AudioPreprocessor",
    "AudioMetadataExtractor",
    "AudioVisionInterpreter",
    "format_audio_to_markdown",
    "get_mock_audio_pipeline_result",
]
