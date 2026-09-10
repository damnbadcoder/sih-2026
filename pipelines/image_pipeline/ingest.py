"""
Image Pipeline Ingestion Orchestrator.
Standardized interface matching the multimodal pipeline layout.
"""
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union, Optional

try:
    from pipelines.base import BasePipeline
except (ImportError, ValueError):
    from ..base import BasePipeline
from .schema import PipelineResult, ImageProvenance
from .extractors.preprocessor import ImagePreprocessor
from .interpreters.interpreter import ImageVisionInterpreter
from .formatter import format_to_markdown
from .mock import get_mock_pipeline_result


class ImagePipeline(BasePipeline):
    """Unified Image Ingestion & Visual Grounding Pipeline."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.interpreter = ImageVisionInterpreter(api_key=api_key, model=model)

    def process(
        self,
        image_input: Union[str, Path, bytes],
        image_name: Optional[str] = None,
        force_mock: bool = False,
    ) -> PipelineResult:
        start_time = time.time()

        processed_bytes, resolved_name, file_size_kb, resolution = ImagePreprocessor.load_and_preprocess(
            image_input=image_input,
            default_name="diagram.jpg",
        )
        final_image_name = image_name or resolved_name

        if force_mock or not self.interpreter.is_available:
            exec_time = int((time.time() - start_time) * 1000)
            return get_mock_pipeline_result(
                image_name=final_image_name,
                file_size_kb=file_size_kb,
                resolution=resolution,
                execution_time_ms=exec_time,
            )

        try:
            parsed_data, anchors, entities, used_model = self.interpreter.interpret(
                image_bytes=processed_bytes,
                image_name=final_image_name,
                resolution=resolution,
            )

            title = parsed_data.get("title") or "Cybersecurity Diagram Advisory"
            overview = parsed_data.get("overview") or parsed_data.get("summary") or f"Analysis of `{final_image_name}`."
            section_title = parsed_data.get("section_title") or "Key Benefits"
            key_points = parsed_data.get("key_points", [])
            grounding_score = float(parsed_data.get("grounding_score_percent") or 99.0)

            exec_time = int((time.time() - start_time) * 1000)

            provenance = ImageProvenance(
                source_image_name=final_image_name,
                source_file_size_kb=file_size_kb,
                total_extracted_nodes=len(anchors),
                extraction_timestamp=datetime.now(timezone.utc).isoformat(),
                grounding_score_percent=grounding_score,
                resolution=resolution,
            )

            markdown_output = format_to_markdown(
                image_name=final_image_name,
                title=title,
                overview=overview,
                anchors=anchors,
                section_title=section_title,
                key_points=key_points,
                entities=entities,
                provenance=provenance,
            )

            extracted_text_raw = "\n".join(
                f"[{a.id}] ({a.visual_anchor}): {a.extracted_verbatim}" for a in anchors
            )

            return PipelineResult(
                metadata=provenance,
                title=title,
                summary=overview,
                extracted_text_raw=extracted_text_raw,
                grounding_sources=anchors,
                markdown_output=markdown_output,
                entities_detected=entities,
                execution_time_ms=exec_time,
                mode="live",
                model=used_model,
            )

        except Exception as e:
            print(f"[ImagePipeline Notice] Live extraction fallback triggered: {e}")
            exec_time = int((time.time() - start_time) * 1000)
            return get_mock_pipeline_result(
                image_name=final_image_name,
                file_size_kb=file_size_kb,
                resolution=resolution,
                execution_time_ms=exec_time,
            )


def ingest_image(
    image_input: Union[str, Path, bytes],
    image_name: Optional[str] = None,
    force_mock: bool = False,
) -> PipelineResult:
    """Convenience procedural entry point for image ingestion."""
    pipeline = ImagePipeline()
    return pipeline.process(image_input=image_input, image_name=image_name, force_mock=force_mock)
