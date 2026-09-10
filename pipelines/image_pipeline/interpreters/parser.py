"""
Response parser and normalizer for model outputs.
"""
import json
from typing import Dict, Any, List, Tuple
from ..schema import GroundingAnchor, EntitiesDetected


class ResponseParser:
    """Parses and sanitizes LLM JSON output into structured representations."""

    @staticmethod
    def clean_json_string(text: str) -> str:
        """Strips markdown code fences and whitespace."""
        s = text.strip()
        if s.startswith("```json"):
            s = s[7:].strip()
        elif s.startswith("```"):
            s = s[3:].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
        return s

    @classmethod
    def parse_payload(cls, raw_response: str) -> Tuple[Dict[str, Any], List[GroundingAnchor], EntitiesDetected]:
        """
        Parses JSON response into metadata dict, grounding anchors, and entities.
        """
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

        anchors: List[GroundingAnchor] = []
        for idx, a in enumerate(anchors_raw):
            if isinstance(a, dict):
                anchors.append(
                    GroundingAnchor(
                        id=str(a.get("id") or f"src-{idx+1}"),
                        visual_anchor=str(a.get("visual_anchor") or a.get("anchor") or "Central Visual Field"),
                        extracted_verbatim=str(a.get("extracted_verbatim") or a.get("text") or a.get("detected_text") or "").strip(),
                        category=str(a.get("category") or a.get("entity_type") or "CORE_CONCEPT"),
                        confidence=float(a.get("confidence") or 0.95),
                    )
                )

        # Fallback anchor if diagram had no text
        if not anchors:
            anchors.append(
                GroundingAnchor(
                    id="src-1",
                    visual_anchor="Full Canvas",
                    extracted_verbatim=str(parsed.get("overview") or parsed.get("summary") or "Visual image tensor verified."),
                    category="CORE_CONCEPT",
                    confidence=1.0,
                )
            )

        # Extract Security Entities
        entities_raw = parsed.get("entities_detected", {})
        cves, actors, targets = [], [], []
        if isinstance(entities_raw, dict):
            cves = entities_raw.get("cves", []) or []
            actors = entities_raw.get("actors", []) or []
            targets = entities_raw.get("targets", []) or []
        elif isinstance(entities_raw, list):
            for item in entities_raw:
                if isinstance(item, str):
                    if item.upper().startswith("CVE"):
                        cves.append(item)
                    else:
                        targets.append(item)
                elif isinstance(item, dict):
                    if "cve" in item:
                        cves.append(str(item["cve"]))
                    if "actor" in item:
                        actors.append(str(item["actor"]))
                    if "target" in item:
                        targets.append(str(item["target"]))

        entities = EntitiesDetected(cves=cves, actors=actors, targets=targets)
        return parsed, anchors, entities
