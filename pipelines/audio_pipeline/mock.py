"""
Deterministic Mock extraction provider for audio pipelines (offline simulation & testing).
"""
from datetime import datetime, timezone
from typing import Optional
from .schema import AudioPipelineResult, AudioGroundingAnchor, AudioProvenance, AudioEntitiesDetected
from .formatter import format_audio_to_markdown


def get_mock_audio_pipeline_result(
    audio_name: str,
    file_size_kb: float = 245.5,
    duration_seconds: Optional[float] = 78.4,
    execution_time_ms: int = 15,
) -> AudioPipelineResult:
    """
    Generates a high-fidelity mock extraction matching an urgent incident triage audio briefing.
    """
    title = "Incident Triage Call: Perimeter Breach & Lateral Propagation Advisory"
    overview = (
        f"Audio recording `{audio_name}` captures an emergency triage briefing discussing an ongoing intrusion [^aud-1]. "
        f"The threat hunting team identified unauthorized memory corruption exploits against the perimeter gateway [^aud-2] "
        f"and confirmed adversary lateral movement toward active domain controllers [^aud-4]."
    )

    anchors = [
        AudioGroundingAnchor(
            id="aud-1",
            temporal_anchor="00:02 - 00:16",
            speaker="Incident Commander",
            extracted_verbatim="Team, we have confirmed anomalous egress traffic originating from the core DMZ subnet. Let's get the telemetry status.",
            category="INCIDENT_ALERT",
            confidence=0.99,
        ),
        AudioGroundingAnchor(
            id="aud-2",
            temporal_anchor="00:18 - 00:34",
            speaker="Lead Threat Hunter",
            extracted_verbatim="Our edge gateway at 192.168.1.1 was hit with an unauthenticated buffer overflow matching CVE-2026-1193, originating from external IP 198.51.100.24.",
            category="VULNERABILITY",
            confidence=0.98,
        ),
        AudioGroundingAnchor(
            id="aud-3",
            temporal_anchor="00:36 - 00:48",
            speaker="SOC Analyst",
            extracted_verbatim="The signature correlates directly to APT-29 Cozy Bear infrastructure beaconing out to c2.apt29-relay.net.",
            category="THREAT_ACTOR",
            confidence=0.97,
        ),
        AudioGroundingAnchor(
            id="aud-4",
            temporal_anchor="00:50 - 01:04",
            speaker="Firewall Administrator",
            extracted_verbatim="Adversary is pivoting laterally across SMB named pipes, attempting credential harvesting against Domain Controller corp-dc01.local.",
            category="TARGET_NODE",
            confidence=0.96,
        ),
        AudioGroundingAnchor(
            id="aud-5",
            temporal_anchor="01:06 - 01:18",
            speaker="Incident Commander",
            extracted_verbatim="Sever the external WAN trunk immediately, revoke active Kerberos golden tickets, and isolate corp-dc01.local.",
            category="DEFENSIVE_ACTION",
            confidence=0.99,
        ),
    ]

    key_points = [
        {
            "label": "Perimeter Ingress Detected",
            "summary": "Emergency triage initiated following confirmed anomalous outbound egress from DMZ.",
            "citation_id": "aud-1",
        },
        {
            "label": "Zero-Day Exploit Disclosure",
            "summary": "Gateway router 192.168.1.1 exploited via unauthenticated RCE flaw CVE-2026-1193.",
            "citation_id": "aud-2",
        },
        {
            "label": "Threat Actor Attribution",
            "summary": "Command-and-control telemetry matches state-sponsored actor APT-29 Cozy Bear.",
            "citation_id": "aud-3",
        },
        {
            "label": "Lateral Movement on Core Identity",
            "summary": "Adversary attempting NTDS.dit extraction on Domain Controller corp-dc01.local.",
            "citation_id": "aud-4",
        },
        {
            "label": "Containment Directives",
            "summary": "Immediate WAN isolation and Kerberos ticket invalidation executed.",
            "citation_id": "aud-5",
        },
    ]

    entities = AudioEntitiesDetected(
        cves=["CVE-2026-1193"],
        actors=["APT-29 (Cozy Bear)"],
        targets=["Edge Gateway Router (192.168.1.1)", "Domain Controller (corp-dc01.local)"],
        iocs_mentioned=["198.51.100.24", "c2.apt29-relay.net", "192.168.1.1"],
    )

    provenance = AudioProvenance(
        source_audio_name=audio_name,
        source_file_size_kb=round(file_size_kb, 2),
        duration_seconds=duration_seconds,
        audio_format="audio/wav",
        total_extracted_nodes=len(anchors),
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        grounding_score_percent=98.5,
    )

    markdown_output = format_audio_to_markdown(
        audio_name=audio_name,
        title=title,
        overview=overview,
        anchors=anchors,
        section_title="Chronological Operational Findings",
        key_points=key_points,
        entities=entities,
        provenance=provenance,
    )

    extracted_text_raw = "\n".join(
        f"[{a.id}] ({a.temporal_anchor}) {a.speaker}: \"{a.extracted_verbatim}\"" for a in anchors
    )

    return AudioPipelineResult(
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
