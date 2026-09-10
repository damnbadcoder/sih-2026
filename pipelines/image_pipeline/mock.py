"""
Deterministic Mock extraction provider for offline testing and fast simulation.
"""
from datetime import datetime, timezone
from typing import Optional, Tuple
from .types import PipelineResult, GroundingAnchor, ImageProvenance, EntitiesDetected
from .formatter import format_to_markdown


def get_mock_pipeline_result(
    image_name: str,
    file_size_kb: float = 128.0,
    resolution: Optional[Tuple[int, int]] = (1087, 611),
    execution_time_ms: int = 12,
) -> PipelineResult:
    """
    Generates a high-fidelity mock extraction matching the NIST Cybersecurity Framework specification.
    """
    title = "NIST Cybersecurity Framework Benefits Advisory"
    overview = "The NIST Cybersecurity Framework provides a comprehensive set of guidelines to help organizations manage and reduce cybersecurity risk [^src-1]."

    anchors = [
        GroundingAnchor(
            id="src-1",
            visual_anchor="Central Hub",
            extracted_verbatim="NIST Cybersecurity framework benefits",
            category="CORE_CONCEPT",
            confidence=0.99,
        ),
        GroundingAnchor(
            id="src-2",
            visual_anchor="Top-Left",
            extracted_verbatim="Risk Management: The framework provides a risk management approach to cybersecurity, enabling organizations to identify, assess, and manage cybersecurity risks.",
            category="BENEFIT",
            confidence=0.95,
        ),
        GroundingAnchor(
            id="src-3",
            visual_anchor="Top-Right",
            extracted_verbatim="Improved Cybersecurity Posture: The NIST Cybersecurity Framework provides a structured approach to managing cybersecurity risks, helping organizations improve their cybersecurity posture.",
            category="BENEFIT",
            confidence=0.95,
        ),
        GroundingAnchor(
            id="src-4",
            visual_anchor="Middle-Right",
            extracted_verbatim="Common Language: The framework provides a common language and structure for discussing cybersecurity risks and controls, facilitating better communication among stakeholders.",
            category="BENEFIT",
            confidence=0.95,
        ),
        GroundingAnchor(
            id="src-5",
            visual_anchor="Bottom-Right",
            extracted_verbatim="Flexibility: The framework is flexible, allowing organizations to tailor it to their specific cybersecurity needs and requirements.",
            category="BENEFIT",
            confidence=0.95,
        ),
        GroundingAnchor(
            id="src-6",
            visual_anchor="Bottom-Left",
            extracted_verbatim="Cost-Effective: The framework provides a cost-effective approach to cybersecurity by enabling organizations to focus their resources on the most critical risks and controls.",
            category="BENEFIT",
            confidence=0.95,
        ),
        GroundingAnchor(
            id="src-7",
            visual_anchor="Middle-Left",
            extracted_verbatim="Compliance: The framework can be used to comply with various cybersecurity regulations and standards, such as the HIPAA, GDPR, and PCI-DSS.",
            category="BENEFIT",
            confidence=0.95,
        ),
    ]

    key_points = [
        {
            "label": "Risk Management",
            "summary": "Establishes a structured approach to identify, assess, and manage risks",
            "citation_id": "src-2",
        },
        {
            "label": "Improved Cybersecurity Posture",
            "summary": "Enhances overall security readiness and resilience",
            "citation_id": "src-3",
        },
        {
            "label": "Common Language",
            "summary": "Facilitates better communication among stakeholders using unified terminology",
            "citation_id": "src-4",
        },
        {
            "label": "Flexibility",
            "summary": "Allows organizations to tailor the framework to their unique requirements",
            "citation_id": "src-5",
        },
        {
            "label": "Cost-Effective",
            "summary": "Focuses resources on the most critical risks and controls",
            "citation_id": "src-6",
        },
        {
            "label": "Compliance",
            "summary": "Assists in meeting regulatory requirements such as HIPAA, GDPR, and PCI-DSS",
            "citation_id": "src-7",
        },
    ]

    entities = EntitiesDetected(
        cves=[],
        actors=[],
        targets=["HIPAA", "GDPR", "PCI-DSS"],
    )

    provenance = ImageProvenance(
        source_image_name=image_name,
        source_file_size_kb=round(file_size_kb, 2),
        total_extracted_nodes=len(anchors),
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        grounding_score_percent=98.5,
        resolution=resolution,
    )

    markdown_output = format_to_markdown(
        image_name=image_name,
        title=title,
        overview=overview,
        anchors=anchors,
        section_title="Key Benefits",
        key_points=key_points,
        entities=entities,
        provenance=provenance,
    )

    extracted_text_raw = "\n".join(f"[{a.id}] ({a.visual_anchor}): {a.extracted_verbatim}" for a in anchors)

    return PipelineResult(
        metadata=provenance,
        title=title,
        summary=overview,
        extracted_text_raw=extracted_text_raw,
        grounding_sources=anchors,
        markdown_output=markdown_output,
        entities_detected=entities,
        execution_time_ms=execution_time_ms,
        mode="mock",
        model="offline-simulation-mock",
    )
