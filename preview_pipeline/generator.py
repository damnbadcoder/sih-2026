import os
import json
from typing import List, Dict, Any, Optional
from .types import (
    MultiPreviewResult, 
    PlatformPreview, 
    SensitiveDataFlag,
    OutputType,
    LinkedInPreviewContent,
    SocialThreadPreviewContent,
    AdvisoryPreviewContent,
    ExecSummaryPreviewContent,
    IncidentReportPreviewContent,
    PressReleasePreviewContent,
    SlideDeckPreviewContent,
    VideoScriptPreviewContent,
    PlaybookPreviewContent,
)
from .proofchecker import scan_and_redact
from .mock import get_mock_previews
from .renderers import RENDERERS

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    from groq import Groq
except ImportError:
    Groq = None

# Platform-specific system prompts for structured generation
PLATFORM_PROMPTS = {
    OutputType.LINKEDIN_POST: """
You are a senior cybersecurity content strategist writing a LinkedIn post for CISOs, SecOps managers, and engineering leaders.
OUTPUT FORMAT: Return ONLY valid JSON matching the LinkedInPreviewContent schema.

REQUIREMENTS:
- hook: ONE punchy opening line (< 150 chars) that creates urgency for leadership
- threat_context: 2-3 sentences summarizing the campaign, actor, and vulnerability exploited
- key_insights: EXACTLY 3 insights - each a complete sentence, business-relevant
- actionable_takeaways: EXACTLY 3 actions - specific, measurable, for SecOps/IT managers
- discussion_prompt: ONE engaging question for comments
- hashtags: 3-5 relevant tags (e.g., #CyberSecurity #CISO #ThreatIntel #DevSecOps)
- citations_used: List of citation markers like ["[^src-1]", "[^src-2]"] used in the content

STYLE: Professional, authoritative, zero fluff. No "In today's world" openings.
""",

    OutputType.SOCIAL_THREAD: """
You are a threat intelligence analyst writing a 5-tweet thread (X/Twitter) for the InfoSec community.
OUTPUT FORMAT: Return ONLY valid JSON matching the SocialThreadPreviewContent schema.

REQUIREMENTS:
- hook_tweet: Tweet 1 - URGENT alert + hook (<=280 chars). Must include 🚨 or 🧵
- exploit_tweet: Tweet 2 - How the exploit works in plain English (<=280 chars)
- ioc_tweet: Tweet 3 - Key IOCs defenders can check NOW (<=280 chars). Include 1-2 concrete indicators
- mitigation_tweet: Tweet 4 - 3 immediate defense steps (<=280 chars). Numbered 1️⃣ 2️⃣ 3️⃣
- wrapup_tweet: Tweet 5 - Official advisory link placeholder + CTA + hashtags (<=280 chars)
- all_tweets: Array of all 5 tweets in order
- citations_used: Citation markers used

STYLE: Technical but accessible. Thread emojis (🧵 👇 🔗). Each tweet standalone but connected.
""",

    OutputType.ADVISORY: """
You are a CERT analyst writing a formal Technical Security Advisory (CISA/CERT style).
OUTPUT FORMAT: Return ONLY valid JSON matching the AdvisoryPreviewContent schema.

REQUIREMENTS:
- tl_protocol: "TLP:AMBER+STRICT" or "TLP:RED" or "TLP:GREEN"
- severity: "CRITICAL" | "HIGH" | "MEDIUM"
- cvss_score: Float (e.g., 9.1) if CVE available, else null
- cve_ids: Array of CVE IDs mentioned in source (e.g., ["CVE-2026-41822"])
- threat_actor: Attributed group name if in source, else null
- affected_systems: Specific platforms/versions from source
- executive_summary: 2-3 sentences for leadership - impact + urgency
- technical_analysis: Detailed exploit chain with MITRE ATT&CK technique IDs (T1190, T1059, etc.)
- iocs: Array of objects: {"type": "IPv4|Domain|Hash|CVE", "indicator": "...", "context": "...", "action": "block|monitor|patch"}
- mitigations: Prioritized numbered steps (1. Immediate, 2. Short-term, 3. Strategic)
- cert_reporting: Official reporting contact if applicable
- citations_used: All citation markers used

STYLE: Formal, precise, actionable. Zero marketing language.
""",

    OutputType.EXEC_SUMMARY: """
You are a CISO's chief of staff writing an Executive Brief for the Board.
OUTPUT FORMAT: Return ONLY valid JSON matching the ExecSummaryPreviewContent schema.

REQUIREMENTS:
- bluf: ONE sentence - Bottom Line Up Front. What happened + business impact.
- situation: 2-3 sentences - operational baseline & threat context
- complication: Business impact - downtime risk, regulatory, brand, legal
- solution: What SOC did - containment, credentials rotated, patches deployed
- strategic_recommendations: 3-4 items - budget, tooling, headcount, policy decisions needed
- citations_used: Citation markers used

STYLE: Executive-ready. No deep technical jargon. Business risk vocabulary.
""",

    OutputType.INCIDENT_REPORT: """
You are a DFIR lead writing an Incident Triage & Forensic Report.
OUTPUT FORMAT: Return ONLY valid JSON matching the IncidentReportPreviewContent schema.

REQUIREMENTS:
- incident_id: "INC-2026-XXXX" format
- status: "CONTAINED" | "UNDER TRIAGE" | "RESOLVED"
- severity: "Tier 1 High" | "Tier 2 Medium" | "Tier 3 Low"
- timeline: Array of {"time": "HH:MM:SS UTC", "event": "..."} - at least 4 entries
- root_cause: Specific vulnerability + injection vector
- blast_radius: Affected hosts, services, credentials - be specific
- corrective_actions: Array of {"action": "...", "status": "complete|in-progress|pending", "owner": "team"}
- citations_used: Citation markers used

STYLE: Forensic precision. UTC timestamps. Evidence-based.
""",

    OutputType.PRESS_RELEASE: """
You are a security communications lead writing a Public Security Advisory.
OUTPUT FORMAT: Return ONLY valid JSON matching the PressReleasePreviewContent schema.

REQUIREMENTS:
- dateline: "CITY — DATE" (e.g., "NEW DELHI — October 12, 2026")
- headline: Reassuring, factual headline
- customer_impact: Explicit "No customer data compromised" or specific impact
- proactive_measures: 3-4 engineering actions taken
- user_guidance: 3-4 safe practices for users
- media_contact: Email/phone for press
- citations_used: Citation markers used

STYLE: Transparent, reassuring, factual. No speculation.
""",

    OutputType.SLIDE_DECK: """
You are a security architect creating a board presentation slide deck.
OUTPUT FORMAT: Return ONLY valid JSON matching the SlideDeckPreviewContent schema.

REQUIREMENTS:
- slides: Array of slide objects with:
  * title: Slide title
  * type: "TITLE_SLIDE" | "TWO_COLUMN" | "TIMELINE" | "CONCLUSION" | "METRICS"
  * key_points: Array of 3-5 bullet points
  * speaker_notes: Talking points for presenter
- citations_used: Citation markers used

SLIDES NEEDED (4-5):
1. TITLE_SLIDE: Executive Overview
2. TWO_COLUMN: Attack Anatomy (left: technical, right: MITRE mapping)
3. TIMELINE: Remediation Roadmap
4. CONCLUSION: Strategic Recommendations
5. Optional METRICS: Dwell time, MTTD, MTTR
""",

    OutputType.VIDEO_SCRIPT: """
You are a threat intelligence video producer writing a 90-second narration script.
OUTPUT FORMAT: Return ONLY valid JSON matching the VideoScriptPreviewContent schema.

REQUIREMENTS:
- runtime_seconds: 90
- scenes: Array of 4 scenes with:
  * scene: "Scene 1 (0:00-0:15)" etc.
  * visual: What's on screen (threat map, animation, checkmarks, logo)
  * narrator: Voice-over script (conversational, urgent but calm)
- citations_used: Citation markers used

SCENES:
1. Hook + Alert (0:00-0:15)
2. Technical Breakdown (0:15-0:45)
3. Defense Directives (0:45-1:15)
4. Conclusion + Resources (1:15-1:30)
""",

    OutputType.PLAYBOOK: """
You are a SOC manager writing an Incident Response Remediation Playbook.
OUTPUT FORMAT: Return ONLY valid JSON matching the PlaybookPreviewContent schema.

REQUIREMENTS:
- playbook_code: "PB-SEC-XX" format
- stages: Array of 4 stages:
  * Stage 1: Identification & Verification (queries, IOC validation)
  * Stage 2: Immediate Containment (isolation, firewall rules, session revocation)
  * Stage 3: Eradication & Recovery (re-image, hash verification, key rotation)
  * Stage 4: Post-Incident (log audit, detection rules, timeline report)
  Each stage: {"stage": 1, "title": "...", "steps": [...], "commands": [...]}
- citations_used: Citation markers used

STYLE: Operational, runbook-ready. Bash commands where applicable.
""",
}

def build_structured_prompt(selected_outputs: List[str], parameters: Dict[str, Any], content_md: str, metadata_json: Dict[str, Any]) -> str:
    """Build a prompt that asks for structured JSON for each selected output type."""
    
    output_instructions = []
    for out in selected_outputs:
        if out in PLATFORM_PROMPTS:
            output_instructions.append(f"=== {out.upper()} ===\n{PLATFORM_PROMPTS[out]}")
    
    outputs_schema = ", ".join(selected_outputs)
    
    return f"""You are an expert cybersecurity content synthesis engine.
Generate structured preview drafts for these output types: {outputs_schema}

PARAMETERS: {json.dumps(parameters)}

SOURCE MATERIAL (Markdown):
{content_md}

METADATA / ANCHORS (JSON):
{json.dumps(metadata_json)}

INSTRUCTIONS:
For EACH output type, generate a JSON object matching its exact schema.
Return a single JSON object with keys = output_type, values = structured content.
Include "citations_used" array in each with markers like "[^src-1]".
Extract key facts from source and include in response as "extracted_facts" array.
Include metadata anchors as "metadata_anchors" object.

{chr(10).join(output_instructions)}

RETURN ONLY VALID JSON. NO MARKDOWN. NO EXPLANATION.
"""


def generate_previews(content_md: str, metadata_json: Dict[str, Any], selected_outputs: List[str], parameters: Dict[str, Any], is_organization: bool = False) -> MultiPreviewResult:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    groq_key = os.environ.get("GROQ_API_KEY")
    groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
    
    prompt = build_structured_prompt(selected_outputs, parameters, content_md, metadata_json)
    data = None

    if gemini_key and genai:
        try:
            client = genai.Client(api_key=gemini_key)
            cfg = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ) if genai_types else {"response_mime_type": "application/json"}
            resp = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=cfg,
            )
            raw = resp.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
        except Exception as e:
            print(f"Gemini preview generation failed ({e}), trying fallback...")

    if data is None and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            gresp = gclient.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": "You are an expert cybersecurity threat intelligence analyst. You output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = json.loads(gresp.choices[0].message.content)
        except Exception as e:
            print(f"Groq preview generation failed ({e}).")

    if data is None:
        return get_mock_previews(content_md, selected_outputs, is_organization)

    result_previews = {}
    extracted_facts = data.get("extracted_facts", [])
    metadata_anchors = data.get("metadata_anchors", {})
    
    for key in selected_outputs:
        if key not in data:
            continue
            
        structured = data[key]
        flags = []
        citations = structured.get("citations_used", [])
        
        # Render to markdown for UI preview
        renderer = RENDERERS.get(key)
        if renderer:
            draft_content = renderer(structured)
        else:
            draft_content = json.dumps(structured, indent=2)
        
        # Apply redaction if Organization mode
        if is_organization:
            draft_content, flags = scan_and_redact(draft_content)
        
        # Build structured content object
        structured_obj = None
        if key == OutputType.LINKEDIN_POST:
            structured_obj = LinkedInPreviewContent(**structured)
        elif key == OutputType.SOCIAL_THREAD:
            structured_obj = SocialThreadPreviewContent(**structured)
        elif key == OutputType.ADVISORY:
            structured_obj = AdvisoryPreviewContent(**structured)
        elif key == OutputType.EXEC_SUMMARY:
            structured_obj = ExecSummaryPreviewContent(**structured)
        elif key == OutputType.INCIDENT_REPORT:
            structured_obj = IncidentReportPreviewContent(**structured)
        elif key == OutputType.PRESS_RELEASE:
            structured_obj = PressReleasePreviewContent(**structured)
        elif key == OutputType.SLIDE_DECK:
            structured_obj = SlideDeckPreviewContent(**structured)
        elif key == OutputType.VIDEO_SCRIPT:
            structured_obj = VideoScriptPreviewContent(**structured)
        elif key == OutputType.PLAYBOOK:
            structured_obj = PlaybookPreviewContent(**structured)
        
        result_previews[key] = PlatformPreview(
            platform_key=key,
            display_name=key.replace("_", " ").title(),
            draft_title=f"{key.replace('_', ' ').title()} Preview",
            draft_content=draft_content,
            structured_content=structured_obj,
            citations_used=citations,
            sensitive_flags=flags
        )
        
    return MultiPreviewResult(
        is_organization=is_organization,
        previews=result_previews,
        source_summary=data.get("source_summary", "") or "Generated from threat intelligence source material.",
        extracted_facts=extracted_facts,
        metadata_anchors=metadata_anchors
    )