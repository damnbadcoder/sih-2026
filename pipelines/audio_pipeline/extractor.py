"""
Audio extractor adapter maintaining signature compatibility.
"""
from typing import Union, Optional
from pathlib import Path
from .schema import AudioPipelineResult
from .ingest import AudioPipeline


class AudioExtractor(AudioPipeline):
    """Alias for AudioPipeline ensuring structural symmetry across pipelines."""
    pass


def process_audio_pipeline(
    audio_input: Union[str, Path, bytes],
    audio_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    force_mock: bool = False,
) -> AudioPipelineResult:
    """Convenience procedural entry point matching standard signature."""
    pipeline = AudioPipeline(api_key=api_key, model=model)
    return pipeline.process(audio_input=audio_input, audio_name=audio_name, force_mock=force_mock)
