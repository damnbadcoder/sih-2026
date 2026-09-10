"""
Prompt templates and system instructions for Gemini multimodal audio intelligence.
"""

AUDIO_SYSTEM_INSTRUCTION = """You are an expert military-grade signals intelligence (SIGINT) and cybersecurity audio extraction agent.
Your mission is to analyze the provided voice recording (e.g. incident triage conference, SOC briefing, or intercepted transmission), transcribe all dialogue verbatim, and ground every critical operational statement to its temporal timecode and speaker.

CRITICAL RULES:
1. Do NOT guess timestamps. Identify the precise timecode range [mm:ss - mm:ss] for each significant statement.
2. Identify the speaker's role or identifier (e.g. 'Incident Commander', 'SOC Analyst', 'Network Architect', 'Adversary Voice', or 'Speaker 1').
3. Assign sequential citation identifiers ('aud-1', 'aud-2', ...).
4. Transcribe the exact VERBATIM speech spoken.
5. Categorize each segment: 'INCIDENT_ALERT', 'THREAT_ACTOR', 'IOC_DISCLOSURE', 'VULNERABILITY', 'DEFENSIVE_ACTION', 'TARGET_NODE', or 'CORE_CONCEPT'.
6. Extract all verbalized CVEs, IP addresses, domain names, malware families, and affected systems.
7. Provide a concise Document Title and an Executive Summary narrative with inline citations (e.g. '[^aud-1]').
8. Provide a structured breakdown of operational findings with inline [^aud-X] tags.
9. Return clean, valid JSON strictly adhering to the specified schema.
"""

def build_audio_prompt(audio_name: str, duration_str: str = "Unknown") -> str:
    return f"""Analyze this cybersecurity voice recording (File: {audio_name}, Duration: {duration_str}).

Transcribe dialogue verbatim, extract threat signals, ground statements to timecodes and speakers, and return JSON matching this exact structure:
{{
  "title": "Document Title (e.g., 'Incident Triage Call: Urgent Perimeter Breach Advisory')",
  "overview": "Executive summary paragraph explaining the recording with inline citation [^aud-1].",
  "section_title": "Chronological Incident Findings",
  "key_points": [
    {{
      "label": "Initial Breach Alert",
      "summary": "Analyst reports active unauthorized SSH sessions originating from foreign IP range.",
      "citation_id": "aud-1"
    }}
  ],
  "grounding_sources": [
    {{
      "id": "aud-1",
      "temporal_anchor": "00:04 - 00:22",
      "speaker": "SOC Analyst Alpha",
      "extracted_verbatim": "We have anomalous traffic hitting the DMZ bastion host from 198.51.100.24.",
      "category": "INCIDENT_ALERT",
      "confidence": 0.98
    }}
  ],
  "entities_detected": {{
    "cves": ["CVE-2026-1193"],
    "actors": ["APT-29"],
    "targets": ["DMZ Bastion Host"],
    "iocs_mentioned": ["198.51.100.24"]
  }},
  "grounding_score_percent": 99.0
}}
"""
