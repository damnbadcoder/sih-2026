from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

class OutputType(str, Enum):
    LINKEDIN_POST = "linkedin_post"
    SOCIAL_THREAD = "social_thread"
    ADVISORY = "advisory"
    EXEC_SUMMARY = "exec_summary"
    INCIDENT_REPORT = "incident_report"
    PRESS_RELEASE = "press_release"
    SLIDE_DECK = "slide_deck"
    VIDEO_SCRIPT = "video_script"
    PLAYBOOK = "playbook"

class SensitiveDataFlag(BaseModel):
    match: str = Field(description="The sensitive data string matched")
    type: str = Field(description="The type of sensitive data (e.g., 'Internal IP', 'Credential')")
    location: Optional[str] = Field(default=None, description="Which field/section this was found in")

class Citation(BaseModel):
    marker: str = Field(description="Citation marker like [^src-1]")
    source_id: str = Field(description="Reference to source citation ID")
    description: str = Field(description="What this citation supports")

# ─── Platform-Specific Structured Content ───

class LinkedInPreviewContent(BaseModel):
    """Structured content for LinkedIn post preview"""
    hook: str = Field(description="Opening line - must grab attention immediately")
    threat_context: str = Field(description="2-3 sentences summarizing the threat/campaign")
    key_insights: List[str] = Field(default_factory=list, description="3 bullet-point insights for engineering leaders")
    actionable_takeaways: List[str] = Field(default_factory=list, description="3 concrete actions for SecOps/IT managers")
    discussion_prompt: str = Field(description="Question to drive comments engagement")
    hashtags: List[str] = Field(default_factory=list, description="3-5 relevant hashtags")
    citations_used: List[str] = Field(default_factory=list, description="Citation markers used in this preview")

class SocialThreadPreviewContent(BaseModel):
    """Structured content for Social Thread (X/Twitter) preview"""
    hook_tweet: str = Field(description="Tweet 1: Urgent alert + hook (<=280 chars)")
    exploit_tweet: str = Field(description="Tweet 2: Exploit mechanism explained simply (<=280 chars)")
    ioc_tweet: str = Field(description="Tweet 3: Key IOCs for defenders (<=280 chars)")
    mitigation_tweet: str = Field(description="Tweet 4: 3 immediate defense steps (<=280 chars)")
    wrapup_tweet: str = Field(description="Tweet 5: Official link + CTA + hashtags (<=280 chars)")
    all_tweets: List[str] = Field(default_factory=list, description="All tweets in order for easy rendering")
    citations_used: List[str] = Field(default_factory=list)

class AdvisoryPreviewContent(BaseModel):
    """Structured content for Technical Advisory preview"""
    tl_protocol: str = Field(default="TLP:AMBER+STRICT", description="Traffic Light Protocol marking")
    severity: str = Field(description="CRITICAL / HIGH / MEDIUM")
    cvss_score: Optional[float] = Field(default=None, description="CVSS v3.1 score if available")
    cve_ids: List[str] = Field(default_factory=list, description="Associated CVE identifiers")
    threat_actor: Optional[str] = Field(default=None, description="Attributed threat actor/group")
    affected_systems: List[str] = Field(default_factory=list, description="Platforms/software versions affected")
    executive_summary: str = Field(description="2-3 sentence operational summary for leadership")
    technical_analysis: str = Field(description="Detailed exploit chain & MITRE ATT&CK mapping")
    iocs: List[Dict[str, str]] = Field(default_factory=list, description="List of {type, indicator, context, action}")
    mitigations: List[str] = Field(default_factory=list, description="Prioritized remediation steps")
    cert_reporting: Optional[str] = Field(default=None, description="CERT contact / reporting instructions")
    citations_used: List[str] = Field(default_factory=list)

class ExecSummaryPreviewContent(BaseModel):
    """Structured content for Executive Summary preview"""
    bluf: str = Field(description="Bottom Line Up Front - 1 sentence")
    situation: str = Field(description="Operational baseline & threat context")
    complication: str = Field(description="Business impact, regulatory exposure, brand risk")
    solution: str = Field(description="Containment actions taken & posture hardening")
    strategic_recommendations: List[str] = Field(default_factory=list, description="Budget/tooling decisions needed")
    citations_used: List[str] = Field(default_factory=list)

class IncidentReportPreviewContent(BaseModel):
    """Structured content for Incident Report preview"""
    incident_id: str = Field(description="INC-YYYY-NNNN format")
    status: str = Field(description="CONTAINED / UNDER TRIAGE / RESOLVED")
    severity: str = Field(description="Tier 1 High / Tier 2 Medium / Tier 3 Low")
    timeline: List[Dict[str, str]] = Field(default_factory=list, description="[{time, event}] in UTC")
    root_cause: str = Field(description="Vulnerability exploited & injection vector")
    blast_radius: List[str] = Field(default_factory=list, description="Affected hosts, services, credentials")
    corrective_actions: List[Dict[str, Any]] = Field(default_factory=list, description="[{action, status, owner}]")
    citations_used: List[str] = Field(default_factory=list)

class PressReleasePreviewContent(BaseModel):
    """Structured content for Press Release preview"""
    dateline: str = Field(description="CITY — DATE format")
    headline: str = Field(description="Clear, reassuring announcement")
    customer_impact: str = Field(description="Explicit data protection confirmation")
    proactive_measures: List[str] = Field(default_factory=list, description="Engineering actions taken")
    user_guidance: List[str] = Field(default_factory=list, description="Safe practices for end-users")
    media_contact: str = Field(description="PR contact details")
    citations_used: List[str] = Field(default_factory=list)

class SlideDeckPreviewContent(BaseModel):
    """Structured content for Slide Deck preview"""
    slides: List[Dict[str, Any]] = Field(default_factory=list, description="[{title, type, key_points[], speaker_notes}]")
    citations_used: List[str] = Field(default_factory=list)

class VideoScriptPreviewContent(BaseModel):
    """Structured content for Video Script preview"""
    runtime_seconds: int = Field(default=90)
    scenes: List[Dict[str, str]] = Field(default_factory=list, description="[{scene, visual, narrator}]")
    citations_used: List[str] = Field(default_factory=list)

class PlaybookPreviewContent(BaseModel):
    """Structured content for Remediation Playbook preview"""
    playbook_code: str = Field(description="e.g., PB-SEC-09")
    stages: List[Dict[str, Any]] = Field(default_factory=list, description="[{stage, title, steps[], commands[]}]")
    citations_used: List[str] = Field(default_factory=list)

# Union of all platform-specific content
PlatformPreviewContent = Union[
    LinkedInPreviewContent,
    SocialThreadPreviewContent,
    AdvisoryPreviewContent,
    ExecSummaryPreviewContent,
    IncidentReportPreviewContent,
    PressReleasePreviewContent,
    SlideDeckPreviewContent,
    VideoScriptPreviewContent,
    PlaybookPreviewContent,
]

class PlatformPreview(BaseModel):
    platform_key: str
    display_name: str
    draft_title: str
    # Keep raw markdown for rendering/display compatibility
    draft_content: str = Field(description="Full rendered markdown for UI preview")
    # Structured content for programmatic access & final pipeline
    structured_content: Optional[PlatformPreviewContent] = None
    citations_used: List[str] = Field(default_factory=list)
    sensitive_flags: List[SensitiveDataFlag] = Field(default_factory=list)

class MultiPreviewResult(BaseModel):
    is_organization: bool
    previews: Dict[str, PlatformPreview]
    source_summary: str = ""
    # Raw extracted facts for grounding the final pipeline
    extracted_facts: List[str] = Field(default_factory=list, description="Key facts extracted from source for final deliverable grounding")
    metadata_anchors: Dict[str, Any] = Field(default_factory=dict, description="Key-value anchors from metadata JSON")