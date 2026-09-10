"""
Markdown document assembler.
Formats extracted visual grounding intelligence into clean, readable advisory reports
matching the standard SIH PS 26154 specification.
"""
from typing import List, Optional, Dict, Any
from .types import GroundingAnchor, ImageProvenance, EntitiesDetected


def format_to_markdown(
    image_name: str,
    title: str,
    overview: str,
    anchors: List[GroundingAnchor],
    section_title: str = "Key Benefits",
    key_points: Optional[List[Dict[str, str]]] = None,
    entities: Optional[EntitiesDetected] = None,
    provenance: Optional[ImageProvenance] = None,
) -> str:
    """
    Assembles a standardized Markdown advisory from extracted diagram intelligence.
    Produces:
    - # {Title}
    - ## Overview
    - ## {Section Title} (Key Benefits / Key Findings)
    - ## Provenance Table
    - Citation footnotes
    """
    lines = [
        f"# {title}",
        f"",
        f"## Overview",
        f"{overview.strip()}",
        f"",
        f"## {section_title}",
    ]

    # Render key points with inline [^src-X] citations
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
        # Generate points directly from anchors if key_points not pre-computed
        for a in anchors:
            # Skip root hub if it's the primary subject
            if a.category == "CORE_CONCEPT" and len(anchors) > 1:
                continue
            text = a.extracted_verbatim
            if ":" in text:
                parts = text.split(":", 1)
                label, body = parts[0].strip(), parts[1].strip()
                lines.append(f"- **{label}**: {body} [^{a.id}]")
            else:
                lines.append(f"- **{a.visual_anchor}**: {text} [^{a.id}]")

    lines.append("")

    # Security Entities (CVEs, Threat Actors, Targets) if present
    if entities and (entities.cves or entities.actors or entities.targets):
        lines.extend([
            f"## Threat & Target Entities",
            f"",
        ])
        if entities.actors:
            lines.append(f"- **Threat Actors**: {', '.join(entities.actors)}")
        if entities.cves:
            lines.append(f"- **Vulnerabilities / CVEs**: {', '.join(entities.cves)}")
        if entities.targets:
            lines.append(f"- **Target Infrastructure / Standards**: {', '.join(entities.targets)}")
        lines.append("")

    # Standard Provenance Table
    lines.extend([
        f"## Provenance Table",
        f"| Source Image | Visual Anchor | Verbatim Text |",
        f"|---|---|---|",
    ])

    for a in anchors:
        safe_text = a.extracted_verbatim.replace("|", "\\|").replace("\n", " ").strip()
        safe_anchor = a.visual_anchor.replace("|", "\\|").strip()
        lines.append(f"| {image_name} | {safe_anchor} | {safe_text} |")

    lines.append("")

    # Footnotes mapping
    for a in anchors:
        safe_text = a.extracted_verbatim.replace("\n", " ").strip()
        lines.append(f"[^{a.id}]: Source: `{image_name}` | Visual Anchor: `{a.visual_anchor}` | Verbatim: \"{safe_text}\"")

    lines.append("")
    return "\n".join(lines)
