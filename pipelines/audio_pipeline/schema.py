"""
Pydantic Schemas for Audio Pipeline.
Provides temporal and speaker grounding models for audio intelligence and wiretaps.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class AudioProvenance(BaseModel):
    """
    Provenance metadata attributing extracted intelligence directly to the source audio file.
    """
    source_audio_name: str = Field(..., description="Name of the source audio file")
    source_file_size_kb: float = Field(..., description="File size in kilobytes")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds")
    audio_format: str = Field(default="audio/wav", description="MIME type or extension (wav, mp3, m4a, ogg)")
    total_extracted_nodes: int = Field(..., description="Total temporal semantic anchors extracted")
    extraction_timestamp: str = Field(..., description="UTC ISO 8601 timestamp of extraction")
    grounding_score_percent: float = Field(default=98.5, description="Attribution / grounding confidence percentage")


class AudioGroundingAnchor(BaseModel):
    """
    Temporal & speaker anchor attributing extracted speech to its timecode interval and speaker.
    Matches the visual anchor pattern with temporal coordinates [start_time - end_time] [Speaker/Role].
    """
    id: str = Field(..., description="Unique citation key, e.g. 'aud-1', 'aud-2'")
    temporal_anchor: str = Field(..., description="Timecode range, e.g. '00:15 - 00:42'")
    speaker: str = Field(default="Unknown Speaker", description="Speaker identity or operational role (e.g., 'Incident Commander', 'SOC Lead')")
    extracted_verbatim: str = Field(..., description="Exact verbatim speech transcribed from the audio recording")
    category: str = Field(default="INCIDENT_ALERT", description="Category: INCIDENT_ALERT, THREAT_ACTOR, IOC_DISCLOSURE, VULNERABILITY, DEFENSIVE_ACTION, TARGET_NODE")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction / transcription confidence score")


class AudioEntitiesDetected(BaseModel):
    """
    Structured threat entities and indicators identified verbally in the audio stream.
    """
    cves: List[str] = Field(default_factory=list, description="CVEs mentioned verbally")
    actors: List[str] = Field(default_factory=list, description="Threat actors or adversary groups named")
    targets: List[str] = Field(default_factory=list, description="Target systems, servers, or enclaves")
    iocs_mentioned: List[str] = Field(default_factory=list, description="IPs, domains, or hashes stated in speech")


class AudioPipelineResult(BaseModel):
    """
    Complete output contract for the audio extraction pipeline.
    """
    metadata: AudioProvenance = Field(..., description="Audio provenance and grounding metadata")
    title: str = Field(default="Audio Intelligence Advisory", description="Inferred or extracted title of the voice briefing")
    summary: str = Field(..., description="Executive narrative summary of the audio recording")
    extracted_text_raw: str = Field(..., description="Complete verbatim transcript of the audio stream")
    grounding_sources: List[AudioGroundingAnchor] = Field(..., description="List of temporal grounding anchors with citation IDs")
    markdown_output: str = Field(..., description="Formatted markdown advisory with inline [^aud-X] citations and provenance table")
    entities_detected: AudioEntitiesDetected = Field(default_factory=AudioEntitiesDetected, description="Detected security entities")
    execution_time_ms: int = Field(..., description="Total end-to-end execution time in milliseconds")
    mode: str = Field(default="live", description="Execution mode ('live' or 'mock')")
    model: str = Field(default="gemini-2.5-flash-lite", description="Underlying model identifier")

    @property
    def anchors(self) -> List[AudioGroundingAnchor]:
        """Convenience accessor for grounding sources."""
        return self.grounding_sources
