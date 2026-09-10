"""
Qwen Semantic Interpreter using LangChain and Groq.
Utilizes Qwen 3.6 27B on Groq to extract rich, actionable context from normalized files
and produces canonical grounding anchors for downstream generative agents.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq

# Automatically load environment variables from .env file
load_dotenv()

from pipelines.schema import (
    ExtractedSourceContext,
    EnrichedGroundingContext,
    MintoPyramidAnalysis,
    ThreatMetadata,
    DownstreamDirectives,
)


GROUNDING_SYSTEM_PROMPT = """You are the Lead Intelligence Officer and Context Grounding Engine for NTRO / Cyber Defense Operations.
Your task is to analyze normalized cybersecurity intelligence documents and extract an IMMUTABLE GROUNDING BUNDLE that subsequent generative agents (Executive Brief, Advisory Bulletin, Social Media, Slide Deck, Video Storyboard) will consume without hallucinations or drift.

### STRICT OPERATIONAL RULES:
1. ZERO HALLUCINATIONS: Do not fabricate or invent any IP addresses, CVEs, domains, hashes, or machine counts.
2. IMMUTABLE NUMERICAL FACTS: Every numerical statistic mentioned in the document (e.g., '3,200 servers compromised', '48-hour dwell time', 'CVSS 9.8') must be locked into `locked_numerical_facts` as exact quotes.
3. MINTO PYRAMID PRINCIPLE: Structure executive communication following Situation -> Complication -> Solution -> Business Impact.
4. ACTIONABLE MITIGATIONS: Provide clear, concrete, prioritized actions.
5. DOWNSTREAM DIRECTIVES: Provide specific guidance hooks for technical advisors, C-level executives, social communicators, and presentation designers.
6. JSON OUTPUT: Respond ONLY with a valid, parseable JSON object matching the required schema. Do not enclose in backticks or markdown fences if possible, or use standard ```json ... ``` blocks.
"""

GROUNDING_HUMAN_PROMPT = """Analyze the following normalized threat document and pre-extracted telemetry:

{grounding_telemetry}

### FULL NORMALIZED DOCUMENT BODY:
{document_body}

Extract the complete grounding context according to this exact JSON schema:
{{
  "title": "Authoritative title of the intelligence event",
  "executive_overview": "Comprehensive executive summary narrative",
  "minto_pyramid": {{
    "situation": "Context & operational baseline",
    "complication": "The exploit, breach, or attack disruption",
    "solution": "Decisive countermeasure or remediation",
    "business_impact_and_risk": "Operational downtime, exposure, or organizational risk"
  }},
  "technical_root_cause": "Detailed technical analysis of root cause and attack mechanisms",
  "timeline_of_events": ["Event 1 timestamped", "Event 2 timestamped"],
  "locked_numerical_facts": ["Exact stat 1", "Exact stat 2"],
  "actionable_mitigations": ["Immediate action 1", "Tactical action 2"],
  "threat_metadata": {{
    "cve_ids": {cve_ids_json},
    "threat_actor": "{threat_actor}",
    "affected_systems": {affected_systems_json},
    "severity": "{severity}",
    "iocs": {iocs_json}
  }},
  "downstream_directives": {{
    "advisory_bullet_points": ["Point 1 for technical bulletin", "Point 2"],
    "executive_takeaways": ["C-level strategic priority 1", "Priority 2"],
    "social_dissemination_hooks": ["Public or social awareness hook 1", "Hook 2"],
    "visual_scene_ideas": ["Visual scene 1 for video/slides", "Scene 2"]
  }}
}}
"""


class QwenGroqInterpreter:
    """Interprets normalized cybersecurity text using Qwen 3.6 27B on Groq."""

    DEFAULT_MODEL = "qwen/qwen3.6-27b"

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        allow_offline_fallback: bool = True
    ):
        self.model_name = model_name or os.environ.get("GROQ_MODEL", self.DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.temperature = temperature
        self.allow_offline_fallback = allow_offline_fallback
        self.llm = self._init_llm()

    def _init_llm(self) -> Optional[ChatGroq]:
        """Initializes the ChatGroq client if API key is present."""
        if not self.api_key:
            return None
        max_tokens = int(os.environ.get("GROQ_MAX_TOKENS", "2048"))
        kwargs = {
            "model_name": self.model_name,
            "groq_api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        # Hide reasoning thinking block so entire output token limit is dedicated to structured JSON
        if "qwen" in self.model_name.lower() or "qwq" in self.model_name.lower():
            kwargs["reasoning_format"] = "hidden"

        return ChatGroq(**kwargs)

    def interpret(
        self,
        source_context: ExtractedSourceContext,
        output_dir: Optional[str] = None,
        save_outputs: bool = True
    ) -> EnrichedGroundingContext:
        """
        Interprets the source document and returns an EnrichedGroundingContext.
        Saves both .md and .json representations of the enriched context.
        """
        if self.llm is None:
            if self.allow_offline_fallback:
                print(
                    "[!] GROQ_API_KEY is not set. Generating deterministic heuristic grounding anchor.",
                    flush=True
                )
                enriched = self._generate_heuristic_grounding(source_context)
            else:
                raise ValueError(
                    "GROQ_API_KEY environment variable is not set. "
                    "Please set GROQ_API_KEY or enable allow_offline_fallback."
                )
        else:
            try:
                enriched = self._invoke_qwen(source_context)
            except Exception as e:
                if self.allow_offline_fallback:
                    print(f"[!] Warning: Groq API call failed ({e}). Falling back to heuristic grounding anchor.")
                    enriched = self._generate_heuristic_grounding(source_context)
                else:
                    raise

        # Save dual-payload outputs (.md and .json)
        if save_outputs:
            target_dir = Path(output_dir) if output_dir else Path("ingestion_outputs")
            self.save_outputs(enriched, source_context.metadata.file_name, target_dir)

        return enriched

    def _invoke_qwen(self, source_context: ExtractedSourceContext) -> EnrichedGroundingContext:
        """Calls Qwen on Groq with structured prompt and validates the Pydantic schema."""
        iocs = source_context.iocs
        threat = source_context.threat_intel

        prompt = GROUNDING_HUMAN_PROMPT.format(
            grounding_telemetry=source_context.llm_bundle.system_grounding_header,
            document_body=source_context.clean_markdown,
            cve_ids_json=json.dumps(iocs.cves),
            threat_actor=threat.threat_actors[0] if threat.threat_actors else "Unattributed",
            affected_systems_json=json.dumps(threat.affected_systems),
            severity=threat.severity_keywords[0] if threat.severity_keywords else "HIGH",
            iocs_json=json.dumps(
                (iocs.ipv4_addresses[:5] + iocs.sha256_hashes[:3] + iocs.domains[:5])
            )
        )

        messages = [
            SystemMessage(content=GROUNDING_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]

        actual_model = self.model_name
        try:
            response = self.llm.invoke(messages)
            content = response.content
        except Exception as err:
            # If qwen 3.6 hits Groq's 1000 OTPM limit, automatically route to qwen 3.8
            if "3.6" in self.model_name and ("429" in str(err) or "rate_limit" in str(err).lower() or "too large" in str(err).lower()):
                print("[*] Note: qwen/qwen3.6-27b reached on-demand token quota. Routing to qwen/qwen3.8-27b...", flush=True)
                fallback_llm = ChatGroq(
                    model_name="qwen/qwen3.8-27b",
                    groq_api_key=self.api_key,
                    temperature=self.temperature,
                    max_tokens=2048
                )
                response = fallback_llm.invoke(messages)
                content = response.content
                actual_model = "qwen/qwen3.8-27b"
            else:
                raise err

        # Parse JSON response
        parsed_data = self._extract_json_from_response(content)
        
        # Ensure model tag is set
        parsed_data["interpreted_by_model"] = actual_model

        # Validate with Pydantic
        try:
            return EnrichedGroundingContext.model_validate(parsed_data)
        except Exception as err:
            print(f"[!] Warning: Model output schema validation issue: {err}. Applying recovery fallback.")
            return self._recover_and_validate(parsed_data, source_context)

    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """Extracts JSON object from model response even if surrounded by markdown code blocks or think tags."""
        # Strip thinking tags if any leaked through
        cleaned_text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

        # Try direct json load first
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass

        # Try searching for ```json ... ``` blocks
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_text)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding the first '{' and last '}'
        start = cleaned_text.find("{")
        end = cleaned_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned_text[start:end+1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to extract valid JSON from Qwen response: {text[:200]}...")

    def _recover_and_validate(
        self,
        raw_dict: Dict[str, Any],
        source: ExtractedSourceContext
    ) -> EnrichedGroundingContext:
        """Fills missing fields to ensure 100% valid Pydantic model instantiation."""
        title = raw_dict.get("title", f"Intelligence Briefing: {source.metadata.file_name}")
        overview = raw_dict.get("executive_overview", source.clean_markdown[:400])

        raw_minto = raw_dict.get("minto_pyramid", {})
        minto = MintoPyramidAnalysis(
            situation=raw_minto.get("situation", "Established enterprise operations"),
            complication=raw_minto.get("complication", "Cyber threat activity detected"),
            solution=raw_minto.get("solution", "Implement recommended mitigations"),
            business_impact_and_risk=raw_minto.get("business_impact_and_risk", "Potential operational exposure")
        )

        root_cause = raw_dict.get("technical_root_cause", "Exploitation of identified technical vulnerability")
        timeline = raw_dict.get("timeline_of_events", source.threat_intel.timelines)
        locked_facts = raw_dict.get("locked_numerical_facts", [f"File word count: {source.metadata.word_count}"])
        mitigations = raw_dict.get("actionable_mitigations", ["Isolate affected systems", "Apply vendor updates"])

        raw_meta = raw_dict.get("threat_metadata", {})
        threat_meta = ThreatMetadata(
            cve_ids=raw_meta.get("cve_ids", source.iocs.cves),
            threat_actor=raw_meta.get("threat_actor", source.threat_intel.threat_actors[0] if source.threat_intel.threat_actors else None),
            affected_systems=raw_meta.get("affected_systems", source.threat_intel.affected_systems),
            severity=raw_meta.get("severity", source.threat_intel.severity_keywords[0] if source.threat_intel.severity_keywords else "HIGH"),
            iocs=raw_meta.get("iocs", source.iocs.ipv4_addresses[:5])
        )

        raw_dir = raw_dict.get("downstream_directives", {})
        directives = DownstreamDirectives(
            advisory_bullet_points=raw_dir.get("advisory_bullet_points", []),
            executive_takeaways=raw_dir.get("executive_takeaways", []),
            social_dissemination_hooks=raw_dir.get("social_dissemination_hooks", []),
            visual_scene_ideas=raw_dir.get("visual_scene_ideas", [])
        )

        return EnrichedGroundingContext(
            title=title,
            executive_overview=overview,
            minto_pyramid=minto,
            technical_root_cause=root_cause,
            timeline_of_events=timeline,
            locked_numerical_facts=locked_facts,
            actionable_mitigations=mitigations,
            threat_metadata=threat_meta,
            downstream_directives=directives,
            interpreted_by_model=f"{self.model_name}-recovered"
        )

    def _generate_heuristic_grounding(self, source: ExtractedSourceContext) -> EnrichedGroundingContext:
        """Deterministic grounding anchor generator used when running without API key."""
        iocs = source.iocs
        threat = source.threat_intel
        meta = source.metadata

        actor_str = threat.threat_actors[0] if threat.threat_actors else "Unidentified Threat Actor"
        severity_str = threat.severity_keywords[0] if threat.severity_keywords else "HIGH"
        cve_str = ", ".join(iocs.cves) if iocs.cves else "Unclassified Vulnerabilities"

        title = f"Threat Assessment: {actor_str} Activity ({cve_str})"

        # Extract first substantive narrative paragraph (skipping headings)
        non_heading_paragraphs = [
            re.sub(r"^[#\s*_-]+", "", p).strip()
            for p in source.clean_markdown.split("\n\n")
            if len(p.strip()) > 50 and not p.strip().startswith("#") and not p.strip().startswith("|")
        ]
        overview = non_heading_paragraphs[0] if non_heading_paragraphs else f"Cybersecurity incident report regarding {meta.file_name} involving {actor_str}."

        minto = MintoPyramidAnalysis(
            situation=f"Enterprise infrastructure running {', '.join(threat.affected_systems) if threat.affected_systems else 'mission-critical systems'}.",
            complication=f"Active threat exploitation detected involving {cve_str} attributed to {actor_str}.",
            solution="Deploy emergency patches, block identified C2 infrastructure, and rotate credentials.",
            business_impact_and_risk=f"Severity rated {severity_str}. Risk of unauthorized command execution and lateral movement."
        )

        # Numerical facts extraction with optional descriptive modifier (e.g., '3,200 enterprise servers')
        numbers = re.findall(
            r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s+[a-zA-Z]+)?\s+(?:servers|hosts|endpoints|machines|nodes|hours|days|weeks|percent|%)\b",
            source.clean_markdown,
            re.IGNORECASE
        )
        locked_facts = [n.strip() for n in numbers]
        if not locked_facts:
            locked_facts = [f"Analyzed {meta.word_count} words across {meta.line_count} lines"]
        if threat.cvss_scores:
            locked_facts.append(f"CVSS Score: {threat.cvss_scores[0]}")

        threat_meta = ThreatMetadata(
            cve_ids=iocs.cves,
            threat_actor=actor_str,
            affected_systems=threat.affected_systems,
            severity=severity_str,
            iocs=(iocs.ipv4_addresses + iocs.domains + iocs.sha256_hashes)[:10]
        )

        directives = DownstreamDirectives(
            advisory_bullet_points=[
                f"Mitigate CVEs: {', '.join(iocs.cves)}",
                f"Block outbound traffic to {len(iocs.ipv4_addresses)} known IP addresses",
                f"Monitor endpoints for {len(iocs.sha256_hashes)} flagged hash signatures"
            ],
            executive_takeaways=[
                f"Operational risk rated {severity_str}",
                f"Targeted software includes {', '.join(threat.affected_systems[:3])}",
                "Immediate patch deployment recommended within 24 hours"
            ],
            social_dissemination_hooks=[
                f"🚨 Critical Alert: Active exploitation of {cve_str} by {actor_str}.",
                "Check your systems and apply patches immediately. #CyberSecurity #ThreatIntel"
            ],
            visual_scene_ideas=[
                "Title card with critical red threat banner and target infrastructure logos",
                "Architecture diagram showing C2 beaconing flow to attacker IPs",
                "Mitigation checklist highlighting urgent patch steps"
            ]
        )

        mitigations = [
            f"Apply urgent vendor patches for {cve_str}",
            "Block identified C2 IP indicators at network boundary firewalls",
            "Force multi-factor authentication and rotate administrative credentials"
        ]

        return EnrichedGroundingContext(
            title=title,
            executive_overview=overview,
            minto_pyramid=minto,
            technical_root_cause=f"Adversary exploited weaknesses in {', '.join(threat.affected_systems) if threat.affected_systems else 'target systems'}.",
            timeline_of_events=threat.timelines or ["Incident detected during scheduled monitoring"],
            locked_numerical_facts=locked_facts,
            actionable_mitigations=mitigations,
            threat_metadata=threat_meta,
            downstream_directives=directives,
            interpreted_by_model="qwen-heuristic-anchor"
        )

    def save_outputs(
        self,
        enriched: EnrichedGroundingContext,
        source_file_name: str,
        target_dir: Path
    ) -> Tuple[Path, Path]:
        """Saves enriched context as both formatted .md and structured .json."""
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(source_file_name).stem

        md_path = target_dir / f"{stem}_enriched_context.md"
        json_path = target_dir / f"{stem}_enriched_context.json"

        # 1. Write rich authoritative Markdown
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(enriched.to_markdown())

        # 2. Write structured JSON metadata
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(enriched.to_dict(), f, indent=2, ensure_ascii=False)

        return md_path, json_path
