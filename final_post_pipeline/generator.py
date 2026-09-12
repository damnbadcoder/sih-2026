# generator.py
import os
import json
from typing import Dict, Any
from .types import FinalDeliverableResult, ProvenanceItem
from .category_prompts import get_prompt_for_category
from .mock import get_mock_final_deliverable

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

def generate_final_deliverable(platform_key: str, approved_draft: str, content_md: str, metadata_json: Dict[str, Any], parameters: Dict[str, Any]) -> FinalDeliverableResult:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    groq_key = os.environ.get("GROQ_API_KEY")
    groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")

    # 1. Extract category-specific system instructions
    system_instruction = get_prompt_for_category(platform_key)
    
    # 2. Structure the prompt using XML-style tags for clear component separation
    prompt = f"""
You must synthesize the <APPROVED_DRAFT> and the <GROUNDING_CONTEXT> to create the final deliverable.
Tailor the output explicitly to these <PARAMETERS>.

<PARAMETERS>
{json.dumps(parameters, indent=2)}
</PARAMETERS>

<METADATA>
{json.dumps(metadata_json, indent=2)}
</METADATA>

<GROUNDING_CONTEXT>
(Use this strictly for factual accuracy, metrics, and technical details. Do not hallucinate outside these facts.)
{content_md}
</GROUNDING_CONTEXT>

<APPROVED_DRAFT>
(Use this as the structural skeleton and thematic direction. Elevate the prose to match the requested platform and tone.)
{approved_draft}
</APPROVED_DRAFT>

OUTPUT INSTRUCTIONS:
Return a valid JSON object exactly matching this schema:
{{
  "final_content": "Your polished, perfectly formatted markdown text here...",
  "provenance": [
    {{"citation_marker": "[^src-1]", "source_reference": "Source Name or URL"}}
  ]
}}
"""
    data = None
    if gemini_key and genai:
        try:
            client = genai.Client(api_key=gemini_key)
            cfg = genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.3,
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
            print(f"Gemini final deliverable generation failed ({e}), trying fallback...")

    if data is None and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            gresp = gclient.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            data = json.loads(gresp.choices[0].message.content)
        except Exception as e:
            print(f"Groq final deliverable generation failed ({e}).")

    if data is None:
        return get_mock_final_deliverable(platform_key, approved_draft)
        
    provenance_list = []
    for item in data.get("provenance", []):
        provenance_list.append(
            ProvenanceItem(
                citation_marker=item.get("citation_marker", ""),
                source_reference=item.get("source_reference", "")
            )
        )
        
    return FinalDeliverableResult(
        platform_key=platform_key,
        final_content=data.get("final_content", approved_draft),
        provenance=provenance_list
    )