"""
Pipelines package for multi-modal cybersecurity content ingestion & transformation.
"""
from pipelines.schema import (
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

def __getattr__(name: str):
    if name == "TextIngestionPipeline":
        from pipelines.ingest import TextIngestionPipeline
        return TextIngestionPipeline
    elif name == "QwenGroqInterpreter":
        from pipelines.interpreters.qwen_interpreter import QwenGroqInterpreter
        return QwenGroqInterpreter
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "TextIngestionPipeline",
    "QwenGroqInterpreter",
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
]
