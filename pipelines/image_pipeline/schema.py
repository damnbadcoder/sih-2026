"""
Pydantic Schemas for Image Pipeline.
Zero-bloat semantic visual grounding contracts replacing numeric 2D bounding boxes.
"""
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class ImageProvenance(BaseModel):
    """
    Provenance metadata attributing extracted intelligence directly to the source image file.
    """
    source_image_name: str = Field(..., description="Name of the source diagram/image file")
    source_file_size_kb: float = Field(..., description="File size in kilobytes")
    total_extracted_nodes: int = Field(..., description="Total visual semantic nodes identified")
    extraction_timestamp: str = Field(..., description="UTC ISO 8601 timestamp of extraction")
    grounding_score_percent: float = Field(default=98.5, description="Attribution / grounding confidence percentage")
    resolution: Optional[Tuple[int, int]] = Field(default=None, description="Image dimensions (width, height)")


class GroundingAnchor(BaseModel):
    """
    Semantic visual anchor attributing extracted text to its relative position/origin in the image.
    Replaces 2D bounding boxes with visual geometry and provenance.
    """
    id: str = Field(..., description="Unique citation key, e.g. 'src-1', 'src-2'")
    visual_anchor: str = Field(..., description="Visual position/origin in image (e.g. 'Top-Left', 'Central Hub')")
    extracted_verbatim: str = Field(..., description="Exact verbatim text read directly from the image node")
    category: str = Field(default="CORE_CONCEPT", description="Entity category: CORE_CONCEPT, BENEFIT, VULNERABILITY, THREAT_ACTOR, ACTION, TARGET_NODE, etc.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction confidence score")


class EntitiesDetected(BaseModel):
    """
    Structured security entities identified in the visual diagram.
    """
    cves: List[str] = Field(default_factory=list, description="Extracted CVE identifiers")
    actors: List[str] = Field(default_factory=list, description="Identified threat actors / adversary groups")
    targets: List[str] = Field(default_factory=list, description="Target nodes, systems, or assets")


class PipelineResult(BaseModel):
    """
    The complete output contract for the image extraction pipeline.
    """
    metadata: ImageProvenance = Field(..., description="Image provenance and grounding metadata")
    title: str = Field(default="Cybersecurity Diagram Advisory", description="Inferred or extracted title of the diagram")
    summary: str = Field(..., description="Overview / narrative summary of the diagram")
    extracted_text_raw: str = Field(..., description="Complete verbatim raw text extracted from the image")
    grounding_sources: List[GroundingAnchor] = Field(..., description="List of visual grounding anchors with citation IDs")
    markdown_output: str = Field(..., description="Formatted markdown advisory with inline [^src-X] citations and provenance table")
    entities_detected: EntitiesDetected = Field(default_factory=EntitiesDetected, description="Detected security entities")
    execution_time_ms: int = Field(..., description="Total end-to-end execution time in milliseconds")
    mode: str = Field(default="live", description="Execution mode ('live' or 'mock')")
    model: str = Field(default="gemini-2.5-flash-lite", description="Underlying model identifier")

    @property
    def anchors(self) -> List[GroundingAnchor]:
        """Convenience property for grounding sources."""
        return self.grounding_sources
