"""
Text Ingestion & Semantic Interpretation Pipeline.
Ingests heterogeneous text documents (PDF, DOCX, MD, TXT, LOG, CSV, JSON),
extracts deterministic IOCs, preserves table structures, processes embedded image OCR,
and provides LLM-based Minto Pyramid grounding anchors.
"""

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


def __getattr__(name: str):
    if name == "TextIngestionPipeline":
        from pipelines.text_pipeline.ingest import TextIngestionPipeline
        return TextIngestionPipeline
    elif name in ("Interpreter", "GroqInterpreter", "QwenGroqInterpreter"):
        from pipelines.text_pipeline.interpreters.interpreter import GroqInterpreter
        return GroqInterpreter
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "TextIngestionPipeline",
    "GroqInterpreter",
    "Interpreter",
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
