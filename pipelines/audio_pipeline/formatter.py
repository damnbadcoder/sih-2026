"""
Markdown document assembler for audio intelligence advisories.
Produces structured advisories with temporal timecode citations [^aud-X] and an auditable provenance table.
"""
from typing import List, Optional, Dict
from .schema import AudioGroundingAnchor, AudioProvenance, AudioEntitiesDetected


def format_audio_to_markdown(
    audio_name: str,
    title: str,
    overview: str,
    anchors: List[AudioGroundingAnchor],
    section_title: str = "Chronological Operational Findings",
    key_points: Optional[List[Dict[str, str]]] = None,
    entities: Optional[AudioEntitiesDetected] = None,
    provenance: Optional[AudioProvenance] = None,
) -> str:
    """
    Assembles a standardized Markdown advisory from extracted audio intelligence.
    """
    lines = [
        f"# {title}",
        f"",
        f"## Overview",
        f"{overview.strip()}",
        f"",
        f"## {section_title}",
    ]

    # Render key points with inline [^aud-X] citations
    if key_points:
        for kp in key_points:
            label = kp.get("label", "").strip()
            summary = kp.get("summary", "").strip()
            cid = kp.get("citation_id", "")
            cite_tag = f" [^{cid}]" if cid else ""
            if label and summary:
                lines.append(f"- **{label}**: {summary}{cite_tag}")
            elif summary:
                lines.append(f"- {summary}{cite_tag}")
    else:
        for a in anchors:
            lines.append(f"- **[{a.speaker}]** ({a.temporal_anchor}): {a.extracted_verbatim} [^{a.id}]")

    lines.append("")

    # Verbalized Threat Entities and Indicators
    if entities and (entities.cves or entities.actors or entities.targets or entities.iocs_mentioned):
        lines.extend([
            f"## Verbalized Threat Entities & Indicators",
            f"",
        ])
        if entities.actors:
            lines.append(f"- **Threat Actors Named**: {', '.join(entities.actors)}")
        if entities.cves:
            lines.append(f"- **CVEs Disclosed**: {', '.join(entities.cves)}")
        if entities.targets:
            lines.append(f"- **Target Infrastructure / Enclaves**: {', '.join(entities.targets)}")
        if entities.iocs_mentioned:
            lines.append(f"- **Spoken IOCs (IPs / Domains)**: {', '.join(f'`{ioc}`' for ioc in entities.iocs_mentioned)}")
        lines.append("")

    # Provenance Table
    lines.extend([
        f"## Provenance & Audio Grounding Table",
        f"| Source Audio | Timestamp Range | Speaker / Role | Verbatim Spoken Text | Category | Confidence |",
        f"|---|---|---|---|---|---|",
    ])

    for a in anchors:
        safe_text = a.extracted_verbatim.replace("|", "\\|").replace("\n", " ").strip()
        safe_anchor = a.temporal_anchor.replace("|", "\\|").strip()
        safe_speaker = a.speaker.replace("|", "\\|").strip()
        lines.append(f"| {audio_name} | `{safe_anchor}` | {safe_speaker} | {safe_text} | `{a.category}` | {a.confidence * 100:.1f}% |")

    lines.append("")

    # Footnotes mapping
    for a in anchors:
        safe_text = a.extracted_verbatim.replace("\n", " ").strip()
        lines.append(
            f"[^{a.id}]: Source: `{audio_name}` | Timecode: `{a.temporal_anchor}` | Speaker: `{a.speaker}` | Verbatim: \"{safe_text}\""
        )

    lines.append("")
    return "\n".join(lines)
