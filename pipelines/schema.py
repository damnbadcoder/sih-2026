"""
Schema definitions for the Ingestion and Pre-LLM Extraction Pipeline.
Aligns with the ExtractedSourceContext contract defined in workflow.md.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class ExtractedIOCs(BaseModel):
    """Deterministic cybersecurity indicators extracted via regex verification."""
    cves: List[str] = Field(default_factory=list, description="Extracted CVE IDs (e.g., CVE-2024-38077)")
    ipv4_addresses: List[str] = Field(default_factory=list, description="Verified IPv4 addresses")
    ipv6_addresses: List[str] = Field(default_factory=list, description="Verified IPv6 addresses")
    sha256_hashes: List[str] = Field(default_factory=list, description="SHA256 file hashes")
    sha1_hashes: List[str] = Field(default_factory=list, description="SHA1 file hashes")
    md5_hashes: List[str] = Field(default_factory=list, description="MD5 file hashes")
    domains: List[str] = Field(default_factory=list, description="Extracted and refanged domain names")
    urls: List[str] = Field(default_factory=list, description="Extracted URLs")
    mitre_attack_ids: List[str] = Field(default_factory=list, description="MITRE ATT&CK technique IDs (e.g., T1059.001)")
    total_iocs_found: int = Field(default=0, description="Total count of all extracted unique indicators")


class TableData(BaseModel):
    """Structured table extracted from document (PDF, DOCX, MD)."""
    table_index: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown_representation: str = Field(description="Formatted Markdown table syntax (| col | col |)")
    row_count: int = 0
    column_count: int = 0


class DocumentMetadata(BaseModel):
    """Structural and file-level metadata."""
    file_name: str
    file_path: str
    file_type: str
    file_size_bytes: int
    sha256_checksum: str
    word_count: int = 0
    character_count: int = 0
    estimated_tokens: int = 0
    line_count: int = 0
    detected_encoding: str = "utf-8"
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ThreatIntelSummary(BaseModel):
    """Preliminary threat intelligence entities and indicators."""
    threat_actors: List[str] = Field(default_factory=list, description="Identified APTs or Threat Actor groups")
    affected_systems: List[str] = Field(default_factory=list, description="Targeted software, OS, or hardware")
    severity_keywords: List[str] = Field(default_factory=list, description="Detected severity ratings (CRITICAL, HIGH, etc.)")
    cvss_scores: List[float] = Field(default_factory=list, description="Extracted CVSS base scores")
    timelines: List[str] = Field(default_factory=list, description="Extracted event dates or timestamp strings")


class SemanticChunk(BaseModel):
    """Contextual text chunk optimized for LLM injection or RAG fallback."""
    chunk_id: int
    parent_section: Optional[str] = None
    text: str
    token_estimate: int
    char_length: int


class LLMInjectionBundle(BaseModel):
    """Optimized payload prepared for downstream LLM prompts and Grounding Agent."""
    system_grounding_header: str = Field(
        description="Formatted pre-prompt injection containing verified IOCs, file telemetry, and tables summary"
    )
    formatted_context_for_prompt: str = Field(
        description="Full curated context string ready to be passed into LLM context window"
    )
    semantic_chunks: List[SemanticChunk] = Field(default_factory=list)


class ExtractedSourceContext(BaseModel):
    """
    Unified Hand-Off Contract (Engineer A -> Engineer B).
    Contains full clean text, extracted tables, deterministic IOCs, structural metadata,
    and LLM-ready prompt injection bundles.
    """
    metadata: DocumentMetadata
    clean_markdown: str = Field(description="Normalized unified Markdown AST representation")
    iocs: ExtractedIOCs
    tables: List[TableData] = Field(default_factory=list)
    threat_intel: ThreatIntelSummary
    llm_bundle: LLMInjectionBundle

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# --- Phase 2: Qwen Semantic Interpretation & Grounding Anchor Schemas ---

class ThreatMetadata(BaseModel):
    """Canonical threat metadata locked into state to prevent drift."""
    cve_ids: List[str] = Field(default_factory=list, description="Associated CVE IDs")
    threat_actor: Optional[str] = Field(default=None, description="Primary APT or threat group identified")
    affected_systems: List[str] = Field(default_factory=list, description="Targeted operating systems, software, or devices")
    severity: str = Field(default="UNKNOWN", description="CRITICAL, HIGH, MEDIUM, LOW")
    iocs: List[str] = Field(default_factory=list, description="Key IPs, Hashes, Domains")


class MintoPyramidAnalysis(BaseModel):
    """Minto Pyramid Principle structure for executive briefing and high-level decisions."""
    situation: str = Field(description="Context and established operational baseline")
    complication: str = Field(description="The incident, exploit, or threat disruption that occurred")
    solution: str = Field(description="The decisive remediation, mitigation, or countermeasure")
    business_impact_and_risk: str = Field(description="Operational downtime, financial exposure, or strategic impact")


class DownstreamDirectives(BaseModel):
    """Contextual directives tailored for downstream specialized generation agents."""
    advisory_bullet_points: List[str] = Field(default_factory=list, description="Key technical highlights for CERT/NTRO advisory")
    executive_takeaways: List[str] = Field(default_factory=list, description="C-level risk decisions and posture guidance")
    social_dissemination_hooks: List[str] = Field(default_factory=list, description="Punchy takeaways and public awareness hooks")
    visual_scene_ideas: List[str] = Field(default_factory=list, description="Keyframe/visual concepts for storyboard and presentation slides")


class EnrichedGroundingContext(BaseModel):
    """
    Rich contextual interpretation produced by Qwen on Groq.
    Acts as the canonical, immutable grounding anchor for all downstream agents.
    """
    title: str = Field(description="Descriptive, authoritative title of the threat advisory / incident")
    executive_overview: str = Field(description="Comprehensive executive narrative explaining the event")
    minto_pyramid: MintoPyramidAnalysis
    technical_root_cause: str = Field(description="Deep dive into initial access vector and exploitation mechanics")
    timeline_of_events: List[str] = Field(default_factory=list, description="Chronological progression of attacker actions or incident timeline")
    locked_numerical_facts: List[str] = Field(default_factory=list, description="Exact numbers, counts, and dates that cannot be altered or drifted by downstream LLMs")
    actionable_mitigations: List[str] = Field(default_factory=list, description="Ordered immediate, tactical, and strategic mitigations")
    threat_metadata: ThreatMetadata
    downstream_directives: DownstreamDirectives
    interpreted_by_model: str = Field(default="qwen/qwen3.6-27b")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_markdown(self) -> str:
        """Converts the rich grounding context into an authoritative Markdown document."""
        md = []
        md.append(f"# 🛡️ {self.title}")
        md.append(f"\n*Interpreted by `{self.interpreted_by_model}` | Generated: {self.generated_at}*")
        md.append(f"\n**Severity:** `{self.threat_metadata.severity}` | **Threat Actor:** `{self.threat_metadata.threat_actor or 'Unattributed'}`\n")

        md.append("## 1. Executive Narrative")
        md.append(self.executive_overview + "\n")

        md.append("## 2. Minto Pyramid Briefing Structure")
        md.append(f"- **Situation:** {self.minto_pyramid.situation}")
        md.append(f"- **Complication:** {self.minto_pyramid.complication}")
        md.append(f"- **Solution:** {self.minto_pyramid.solution}")
        md.append(f"- **Business & Operational Impact:** {self.minto_pyramid.business_impact_and_risk}\n")

        md.append("## 3. Technical Root Cause & Attack Vector")
        md.append(self.technical_root_cause + "\n")

        if self.timeline_of_events:
            md.append("## 4. Timeline of Incident Progression")
            for item in self.timeline_of_events:
                md.append(f"- {item}")
            md.append("")

        if self.locked_numerical_facts:
            md.append("## 5. Canonical Grounding Facts (Immutable Metrics)")
            for fact in self.locked_numerical_facts:
                md.append(f"- 📌 **{fact}**")
            md.append("")

        if self.threat_metadata.cve_ids or self.threat_metadata.affected_systems:
            md.append("## 6. Threat Telemetry & Target Infrastructure")
            if self.threat_metadata.cve_ids:
                md.append(f"- **Associated CVEs:** {', '.join(self.threat_metadata.cve_ids)}")
            if self.threat_metadata.affected_systems:
                md.append(f"- **Affected Systems:** {', '.join(self.threat_metadata.affected_systems)}")
            if self.threat_metadata.iocs:
                md.append(f"- **Key IOCs:** {', '.join(self.threat_metadata.iocs)}")
            md.append("")

        if self.actionable_mitigations:
            md.append("## 7. Actionable Mitigations")
            for idx, action in enumerate(self.actionable_mitigations, start=1):
                md.append(f"{idx}. {action}")
            md.append("")

        md.append("## 8. Downstream LLM Guidance Directives")
        if self.downstream_directives.advisory_bullet_points:
            md.append("### Advisory Highlights")
            for p in self.downstream_directives.advisory_bullet_points:
                md.append(f"- {p}")
        if self.downstream_directives.executive_takeaways:
            md.append("\n### Executive Takeaways")
            for p in self.downstream_directives.executive_takeaways:
                md.append(f"- {p}")
        if self.downstream_directives.social_dissemination_hooks:
            md.append("\n### Social Media Hooks")
            for p in self.downstream_directives.social_dissemination_hooks:
                md.append(f"- {p}")
        if self.downstream_directives.visual_scene_ideas:
            md.append("\n### Storyboard & Slide Visual Themes")
            for p in self.downstream_directives.visual_scene_ideas:
                md.append(f"- {p}")

        return "\n".join(md)

