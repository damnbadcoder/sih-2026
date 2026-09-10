"""
Prompt templates and system instructions for Gemini multimodal vision grounding.
"""

SYSTEM_INSTRUCTION = """You are an expert military-grade document and cybersecurity diagram extraction agent.
Your mission is to extract ALL visual concepts, text nodes, and labels verbatim from the image, and ground each one to its visual anchor in the diagram.

CRITICAL RULES:
1. Do NOT generate numeric 2D coordinates, pixel matrices, or bounding boxes.
2. For every concept or text segment, tag its relative visual origin / geometry (e.g. 'Central Hub', 'Top-Left', 'Top-Right', 'Middle-Right', 'Bottom-Right', 'Bottom-Left', 'Middle-Left').
3. Assign sequential citation identifiers ('src-1', 'src-2', ...).
4. Extract the exact VERBATIM text read from the image.
5. Provide a clear Document Title (e.g. 'NIST Cybersecurity Framework Benefits Advisory').
6. Provide an Overview paragraph describing the core subject with an inline citation to the primary hub node (e.g. '[^src-1]').
7. Provide a list of key points / benefits / findings with a bold label, a concise summary, and the corresponding citation '[^src-X]'.
8. Identify any specific CVEs, threat actors, and target entities.
9. Return clean, valid JSON strictly adhering to the specified schema.
"""

def build_extraction_prompt(image_name: str, resolution: tuple[int, int]) -> str:
    return f"""Analyze this cybersecurity diagram (Filename: {image_name}, Resolution: {resolution[0]}x{resolution[1]}).

Extract all text verbatim, ground every node to its visual origin anchor, and return a JSON object with this exact structure:
{{
  "title": "Document Title (e.g., 'NIST Cybersecurity Framework Benefits Advisory')",
  "overview": "Comprehensive overview paragraph explaining the diagram with inline citation [^src-1].",
  "section_title": "Key Benefits" (or "Key Findings" / "Incident Analysis"),
  "key_points": [
    {{
      "label": "Risk Management",
      "summary": "Establishes a structured approach to identify, assess, and manage risks.",
      "citation_id": "src-2"
    }}
  ],
  "grounding_sources": [
    {{
      "id": "src-1",
      "visual_anchor": "Central Hub",
      "extracted_verbatim": "NIST Cybersecurity framework benefits",
      "category": "CORE_CONCEPT",
      "confidence": 0.99
    }},
    {{
      "id": "src-2",
      "visual_anchor": "Top-Left",
      "extracted_verbatim": "Risk Management: The framework provides a risk management approach to cybersecurity...",
      "category": "BENEFIT",
      "confidence": 0.95
    }}
  ],
  "entities_detected": {{
    "cves": [],
    "actors": [],
    "targets": ["HIPAA", "GDPR", "PCI-DSS"]
  }},
  "grounding_score_percent": 98.5
}}
"""
