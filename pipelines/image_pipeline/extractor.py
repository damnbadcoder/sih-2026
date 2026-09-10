"""
Extractor adapter maintaining full backward compatibility with process_image_pipeline.
"""
from typing import Union, Optional
from pathlib import Path
from .schema import PipelineResult
from .ingest import ImagePipeline


class ImageExtractor(ImagePipeline):
    """Alias for ImagePipeline ensuring zero breaking changes."""
    pass


def process_image_pipeline(
    image_input: Union[str, Path, bytes],
    image_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    force_mock: bool = False,
) -> PipelineResult:
    """Convenience procedural entry point matching legacy signature."""
    pipeline = ImagePipeline(api_key=api_key, model=model)
    return pipeline.process(image_input=image_input, image_name=image_name, force_mock=force_mock)
