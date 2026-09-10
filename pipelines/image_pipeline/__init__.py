"""
Image Ingestion & Grounding Pipeline for NTRO PS 26154.
Modular visual semantic attribution pipeline matching the project layout.
"""
from .schema import PipelineResult, GroundingAnchor, ImageProvenance, EntitiesDetected
from .ingest import ImagePipeline, ingest_image
from .extractor import ImageExtractor, process_image_pipeline
from .extractors.preprocessor import ImagePreprocessor
from .extractors.ocr_utils import ImageOCRUtils
from .interpreters.interpreter import ImageVisionInterpreter
from .formatter import format_to_markdown
from .mock import get_mock_pipeline_result

__all__ = [
    "ImagePipeline",
    "ingest_image",
    "ImageExtractor",
    "process_image_pipeline",
    "PipelineResult",
    "GroundingAnchor",
    "ImageProvenance",
    "EntitiesDetected",
    "ImagePreprocessor",
    "ImageOCRUtils",
    "ImageVisionInterpreter",
    "format_to_markdown",
    "get_mock_pipeline_result",
]
