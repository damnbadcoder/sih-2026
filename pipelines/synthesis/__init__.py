"""
Synthesis Pipeline Package (Person A & Person B Orchestration).
Bridges multimodal pipeline extraction, preview generation, sensitive proofchecking,
and final deliverable synthesis.
"""

from preview_pipeline.types import (
    OutputType as PlatformOutputType,
    PlatformPreview,
    MultiPreviewResult,
    SensitiveDataFlag,
)
from preview_pipeline import generate_previews, scan_and_redact
from final_post_pipeline import generate_final_deliverable, FinalDeliverableResult

# Backward compatibility contract matching tests/test_person_a.py & experiments/shared_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class OutputType(str, Enum):
    ADVISORY = "advisory"
    EXECUTIVE_SUMMARY = "executive_summary"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    PRESENTATION = "presentation"
    VIDEO_PACKAGE = "video_package"
    INFOGRAPHIC = "infographic"


class UserConfig(BaseModel):
    output_type: OutputType
    audience_category: str = Field(default="Technical")
    target_audience: str = Field(default="")
    tone: str = Field(default="Professional")
    detail_level: str = Field(default="Medium")
    objective: str = Field(default="Inform")
    language: str = Field(default="English")


class Citation(BaseModel):
    id: str
    claim: str
    source_type: str = "text"
    verbatim_quote: str = ""


class SectionOutline(BaseModel):
    heading: str
    key_points: List[str]
    tone_note: str = ""
    citations_used: List[str] = Field(default_factory=list)


class DeliverableOutline(BaseModel):
    output_type: OutputType
    config: UserConfig
    proposed_title: str
    sections: List[SectionOutline]
    estimated_length: str
    overall_approach: str
    user_edits: str = ""


class PreviewBundle(BaseModel):
    plan_narrative: str
    citations: List[Citation]
    outlines: List[DeliverableOutline]


def generate_preview(content_md: str, metadata_json: Any = None, configs: Any = None) -> PreviewBundle:
    """
    Compatibility wrapper matching tests/test_person_a.py signature.
    """
    if metadata_json is None:
        metadata_json = {}
    if configs is None:
        configs = []

    selected = []
    outlines = []
    for cfg in configs:
        ot = getattr(cfg, "output_type", None)
        val = ot.value if hasattr(ot, "value") else str(ot)
        key_map = {
            "advisory": "advisory",
            "executive_summary": "exec_summary",
            "linkedin": "linkedin_post",
            "twitter": "social_thread",
            "presentation": "slide_deck",
            "video_package": "video_script",
            "infographic": "playbook",
        }
        mapped_key = key_map.get(val, "advisory")
        selected.append(mapped_key)

    if not selected:
        selected = ["advisory", "exec_summary", "linkedin_post"]

    multi_res = generate_previews(
        content_md=content_md,
        metadata_json=metadata_json if isinstance(metadata_json, dict) else {},
        selected_outputs=selected,
        parameters={"audienceCategory": "Technical", "tone": "Professional"},
        is_organization=False,
    )

    extracted_citations = [
        Citation(id=f"src-{i+1}", claim=fact, source_type="text")
        for i, fact in enumerate(multi_res.extracted_facts or ["Primary telemetry verified."])
    ]

    for cfg in configs:
        ot = getattr(cfg, "output_type", None)
        val = ot.value if hasattr(ot, "value") else str(ot)
        key_map = {
            "advisory": "advisory",
            "executive_summary": "exec_summary",
            "linkedin": "linkedin_post",
            "twitter": "social_thread",
            "presentation": "slide_deck",
            "video_package": "video_script",
            "infographic": "playbook",
        }
        pkey = key_map.get(val, "advisory")
        p_obj = multi_res.previews.get(pkey)
        draft_text = p_obj.draft_content if p_obj else ""

        sections = [
            SectionOutline(
                heading=f"{val.replace('_', ' ').title()} Core Structure",
                key_points=[line.strip() for line in draft_text.split("\n") if line.strip()][:4],
                tone_note=getattr(cfg, "tone", "Professional"),
                citations_used=p_obj.citations_used if p_obj else ["src-1"],
            )
        ]

        outlines.append(
            DeliverableOutline(
                output_type=cfg.output_type if isinstance(cfg.output_type, OutputType) else OutputType.ADVISORY,
                config=cfg,
                proposed_title=p_obj.draft_title if p_obj else f"{val.title()} Draft",
                sections=sections,
                estimated_length="Standard",
                overall_approach=f"Tailored for {getattr(cfg, 'target_audience', 'analysts')}",
            )
        )

    return PreviewBundle(
        plan_narrative=multi_res.source_summary,
        citations=extracted_citations,
        outlines=outlines,
    )


__all__ = [
    "OutputType",
    "UserConfig",
    "Citation",
    "SectionOutline",
    "DeliverableOutline",
    "PreviewBundle",
    "generate_preview",
    "generate_previews",
    "generate_final_deliverable",
    "scan_and_redact",
]
