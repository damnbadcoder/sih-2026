"""
Extractors package for the multimodal video pipeline.
"""

from pipelines.video_pipeline.extractors.audio_extractor import VideoAudioExtractor
from pipelines.video_pipeline.extractors.scene_detector import VideoSceneDetector
from pipelines.video_pipeline.extractors.visual_classifier import KeyframeVisualClassifier
from pipelines.video_pipeline.extractors.specialized_extractors import SpecializedContentExtractor
from pipelines.video_pipeline.extractors.temporal_aligner import TemporalMultimodalAligner

__all__ = [
    "VideoAudioExtractor",
    "VideoSceneDetector",
    "KeyframeVisualClassifier",
    "SpecializedContentExtractor",
    "TemporalMultimodalAligner",
]
