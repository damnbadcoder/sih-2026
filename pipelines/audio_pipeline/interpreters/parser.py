"""
Response parser and normalizer for audio model outputs.
"""
import json
from typing import Dict, Any, List, Tuple
from ..schema import AudioGroundingAnchor, AudioEntitiesDetected


class AudioResponseParser:
    """Parses and sanitizes LLM JSON output from audio intelligence queries."""

    @staticmethod
    def clean_json_string(text: str) -> str:
        s = text.strip()
        if s.startswith("```json"):
            s = s[7:].strip()
        elif s.startswith("```"):
            s = s[3:].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
        return s

    @classmethod
    def parse_payload(cls, raw_response: str) -> Tuple[Dict[str, Any], List[AudioGroundingAnchor], AudioEntitiesDetected]:
        clean_text = cls.clean_json_string(raw_response)
        parsed = json.loads(clean_text)

        if isinstance(parsed, list):
            if len(parsed) > 0 and isinstance(parsed[0], dict):
                parsed = parsed[0]
            else:
                parsed = {"grounding_sources": []}
        elif not isinstance(parsed, dict):
            parsed = {"summary": str(parsed), "grounding_sources": []}

        # Extract Anchors
        anchors_raw = parsed.get("grounding_sources", []) or parsed.get("anchors", [])
        if isinstance(anchors_raw, dict):
            anchors_raw = [anchors_raw]
        elif not isinstance(anchors_raw, list):
            anchors_raw = []

        anchors: List[AudioGroundingAnchor] = []
        for idx, a in enumerate(anchors_raw):
            if isinstance(a, dict):
                anchors.append(
                    AudioGroundingAnchor(
                        id=str(a.get("id") or f"aud-{idx+1}"),
                        temporal_anchor=str(a.get("temporal_anchor") or a.get("timestamp") or a.get("timecode") or "00:00 - 00:30"),
                        speaker=str(a.get("speaker") or a.get("speaker_role") or "Speaker 1"),
                        extracted_verbatim=str(a.get("extracted_verbatim") or a.get("text") or a.get("transcript") or "").strip(),
                        category=str(a.get("category") or "INCIDENT_ALERT"),
                        confidence=float(a.get("confidence") or 0.95),
                    )
                )

        if not anchors:
            anchors.append(
                AudioGroundingAnchor(
                    id="aud-1",
                    temporal_anchor="00:00 - End",
                    speaker="Audio Feed",
                    extracted_verbatim=str(parsed.get("overview") or parsed.get("summary") or "Audio stream analyzed."),
                    category="INCIDENT_ALERT",
                    confidence=1.0,
                )
            )

        # Extract Security Entities
        entities_raw = parsed.get("entities_detected", {})
        cves, actors, targets, iocs = [], [], [], []
        if isinstance(entities_raw, dict):
            cves = entities_raw.get("cves", []) or []
            actors = entities_raw.get("actors", []) or []
            targets = entities_raw.get("targets", []) or []
            iocs = entities_raw.get("iocs_mentioned", []) or entities_raw.get("iocs", []) or []
        elif isinstance(entities_raw, list):
            for item in entities_raw:
                if isinstance(item, str):
                    if item.upper().startswith("CVE"):
                        cves.append(item)
                    else:
                        targets.append(item)

        entities = AudioEntitiesDetected(
            cves=cves,
            actors=actors,
            targets=targets,
            iocs_mentioned=iocs,
        )
        return parsed, anchors, entities
