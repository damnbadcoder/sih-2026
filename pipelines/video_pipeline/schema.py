"""
Pydantic Schemas and Contracts for the Multimodal Video Ingestion Pipeline.
Defines aligned multimodal structures capturing visual keyframes, audio transcripts,
and deterministic cybersecurity intelligence telemetry.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class VisualType(str, Enum):
    """Classification category for extracted keyframes."""
    SLIDE = "SLIDE"          # Presentation slides with text, headings, bullet points
    TERMINAL = "TERMINAL"    # Shell, console, command-line logs, source code
    DIAGRAM = "DIAGRAM"      # System architecture, network flow, attack tree
    OTHER = "OTHER"          # Camera feeds, talking heads, intro cards


class ExtractedVideoIOCs(BaseModel):
    """Deterministic cybersecurity indicators extracted from both audio and visual streams."""
    cves: List[str] = Field(default_factory=list)
    ipv4_addresses: List[str] = Field(default_factory=list)
    ipv6_addresses: List[str] = Field(default_factory=list)
    sha256_hashes: List[str] = Field(default_factory=list)
    md5_hashes: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)
    mitre_attack_ids: List[str] = Field(default_factory=list)
    total_iocs_found: int = 0


class AudioSegment(BaseModel):
    """Timestamped spoken segment from video audio track."""
    segment_id: int
    start_seconds: float
    end_seconds: float
    text: str


class KeyframeInfo(BaseModel):
    """Metadata for a unique, deduplicated keyframe image."""
    frame_index: int
    timestamp_seconds: float
    image_path: str
    perceptual_hash: str
    visual_type: VisualType = VisualType.OTHER


class VisualContent(BaseModel):
    """Extracted and specialized content for a keyframe."""
    visual_type: VisualType
    raw_ocr_text: str = ""
    structured_content: str = ""
    mermaid_diagram: Optional[str] = None
    code_snippet: Optional[str] = None
    extracted_iocs: List[str] = Field(default_factory=list)
    visual_narrative: str = ""


class AlignedScene(BaseModel):
    """
    Temporally aligned multimodal unit.
    Captures what was VISIBLE on screen alongside what was SPOKEN during that exact timeframe.
    """
    scene_id: int
    start_seconds: float
    end_seconds: float
    timestamp_display: str
    keyframe: KeyframeInfo
    visual: VisualContent
    spoken_transcript: str
    scene_iocs: List[str] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    """Technical telemetry of the ingested video file."""
    file_name: str
    file_path: str
    file_size_bytes: int
    sha256_checksum: str
    duration_seconds: float
    fps: float
    resolution: str
    total_frames: int
    has_audio: bool
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExtractedVideoContext(BaseModel):
    """
    Master hand-off contract for video ingestion.
    Contains aligned scenes, synchronized transcripts, visual OCR, diagrams, and IOCs.
    """
    metadata: VideoMetadata
    scenes: List[AlignedScene] = Field(default_factory=list)
    full_audio_transcript: str = ""
    iocs: ExtractedVideoIOCs = Field(default_factory=ExtractedVideoIOCs)
    clean_markdown: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class VideoMintoPyramid(BaseModel):
    situation: str = Field(description="Operational context established in briefing")
    complication: str = Field(description="Exploit demonstration, breach, or vulnerability shown")
    solution: str = Field(description="Mitigations or patches presented")
    business_impact_and_risk: str = Field(description="Operational risk and downtime impact")


class VideoEnrichedGroundingContext(BaseModel):
    """Canonical grounding anchor produced by LLM interpretation of video context."""
    title: str
    executive_overview: str
    minto_pyramid: VideoMintoPyramid
    technical_root_cause: str
    timeline_of_events: List[str] = Field(default_factory=list)
    locked_numerical_facts: List[str] = Field(default_factory=list)
    actionable_mitigations: List[str] = Field(default_factory=list)
    indicators_of_compromise: Optional[ExtractedVideoIOCs] = None
    interpreted_by_model: str = "groq-model"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_markdown(self) -> str:
        md = [
            f"# 🎥 {self.title}",
            f"\n*Interpreted by `{self.interpreted_by_model}` | Generated: {self.generated_at}*\n",
            "## 1. Executive Narrative",
            self.executive_overview + "\n",
            "## 2. Minto Pyramid Briefing Structure",
            f"- **Situation:** {self.minto_pyramid.situation}",
            f"- **Complication:** {self.minto_pyramid.complication}",
            f"- **Solution:** {self.minto_pyramid.solution}",
            f"- **Business Impact:** {self.minto_pyramid.business_impact_and_risk}\n",
            "## 3. Technical Root Cause & Exploit Mechanics",
            self.technical_root_cause + "\n",
        ]
        if self.locked_numerical_facts:
            md.append("## 4. Canonical Grounding Facts (Locked Metrics)")
            for f in self.locked_numerical_facts:
                md.append(f"- 📌 **{f}**")
            md.append("")
        if self.timeline_of_events:
            md.append("## 5. Timeline of Events")
            for t in self.timeline_of_events:
                md.append(f"- {t}")
            md.append("")
        if self.actionable_mitigations:
            md.append("## 6. Actionable Mitigations")
            for idx, m in enumerate(self.actionable_mitigations, start=1):
                md.append(f"{idx}. {m}")
            md.append("")
        if self.indicators_of_compromise:
            ioc = self.indicators_of_compromise
            md.append("## 7. Indicators of Compromise")
            if ioc.cves:
                md.append(f"- **CVEs:** {', '.join(ioc.cves)}")
            if ioc.ipv4_addresses:
                md.append(f"- **IP Addresses:** {', '.join(ioc.ipv4_addresses)}")
            if ioc.sha256_hashes:
                md.append(f"- **SHA-256 Hashes:** {', '.join(ioc.sha256_hashes)}")
            if ioc.domains or ioc.urls:
                md.append(f"- **Domains / URLs:** {', '.join(ioc.domains + ioc.urls)}")
            md.append("")
        return "\n".join(md)
