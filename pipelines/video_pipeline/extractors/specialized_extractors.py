"""
Specialized Content Extractors for Classified Keyframes.
Tailored processors for SLIDE, TERMINAL, DIAGRAM, and OTHER visual types.
Generates structured Markdown, Mermaid.js diagrams, formatted shell code blocks,
and deterministic cybersecurity indicator inventories.
"""

import os
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

from pipelines.video_pipeline.schema import VisualType, VisualContent
from pipelines.text_pipeline.extractors.ocr_utils import extract_text_from_image_bytes
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


DIAGRAM_MERMAID_PROMPT = """You are a Cybersecurity Architecture and Diagram Specialist.
Convert the following extracted OCR text and structural nodes from an incident architecture/attack diagram into:
1. A valid, syntax-clean Mermaid.js flowchart (using `flowchart TD` or `flowchart LR`).
2. A brief 2-3 sentence architectural narrative explaining the network/data flow.

### OCR & Visual Node Clues:
{ocr_text}

OUTPUT FORMAT:
Respond ONLY with the Mermaid code block followed by the narrative.
Example:
```mermaid
flowchart LR
    A[Attacker] -->|Spearphish| B[Perimeter DMZ]
    B -->|Lateral Move| C[Domain Controller]
```
Narrative: The attacker moves from the perimeter DMZ to the internal domain controller via lateral movement.
"""


class SpecializedContentExtractor:
    """Dispatches keyframe images to specialized extractors based on their VisualType."""

    def __init__(self, groq_api_key: Optional[str] = None):
        self.api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.api_key) if (GROQ_AVAILABLE and self.api_key) else None
        self.ioc_extractor = IOCExtractor()

    def process_keyframe(self, image_path: str, visual_type: VisualType) -> VisualContent:
        """
        Extracts specialized structured content according to visual type.

        Args:
            image_path: Path to keyframe image.
            visual_type: Classified type (SLIDE, TERMINAL, DIAGRAM, OTHER).

        Returns:
            VisualContent object with typed extraction assets.
        """
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        raw_ocr = extract_text_from_image_bytes(image_bytes, min_length=2)
        extracted_iocs = self.ioc_extractor.extract_iocs(raw_ocr)

        ioc_list: List[str] = []
        ioc_list.extend(extracted_iocs.cves)
        ioc_list.extend(extracted_iocs.ipv4_addresses)
        ioc_list.extend(extracted_iocs.sha256_hashes)
        ioc_list.extend(extracted_iocs.domains)

        if visual_type == VisualType.SLIDE:
            return self._extract_slide(raw_ocr, ioc_list)
        elif visual_type == VisualType.TERMINAL:
            return self._extract_terminal(raw_ocr, ioc_list)
        elif visual_type == VisualType.DIAGRAM:
            return self._extract_diagram(raw_ocr, ioc_list)
        else:
            return self._extract_other(raw_ocr, ioc_list)

    def _extract_slide(self, raw_ocr: str, iocs: List[str]) -> VisualContent:
        """Processes presentation slides, structuring verbatim bullet points and headings."""
        lines = [line.strip() for line in raw_ocr.splitlines() if line.strip()]
        if not lines:
            return VisualContent(visual_type=VisualType.SLIDE, raw_ocr_text="", structured_content="*(Empty slide)*")

        title = lines[0]
        bullet_lines = lines[1:]

        md_blocks = [f"#### 📑 Slide: {title}"]
        for b in bullet_lines:
            if not b.startswith(("-", "*", "•")):
                b = f"- {b}"
            md_blocks.append(b)

        structured_md = "\n".join(md_blocks)
        return VisualContent(
            visual_type=VisualType.SLIDE,
            raw_ocr_text=raw_ocr,
            structured_content=structured_md,
            extracted_iocs=iocs,
            visual_narrative=f"Presentation slide covering: {title}"
        )

    def _extract_terminal(self, raw_ocr: str, iocs: List[str]) -> VisualContent:
        """Processes shell/console captures, applying bash syntax formatting and file path extraction."""
        # Detect Linux/Windows file paths
        path_pattern = re.compile(r"(?:/[a-zA-Z0-9_\.\-]+)+|(?:[C-Z]:\\[a-zA-Z0-9_\.\-\\]+)")
        detected_paths = path_pattern.findall(raw_ocr)

        # Format as shell code block
        code_block = f"```bash\n{raw_ocr}\n```"
        structured_md = f"#### 💻 Terminal Session / Shell Output\n\n{code_block}"
        if detected_paths:
            structured_md += f"\n*Referenced Paths:* `{', '.join(detected_paths[:5])}`"

        return VisualContent(
            visual_type=VisualType.TERMINAL,
            raw_ocr_text=raw_ocr,
            structured_content=structured_md,
            code_snippet=raw_ocr,
            extracted_iocs=iocs,
            visual_narrative="Active command-line console session displaying terminal execution logs."
        )

    def _extract_diagram(self, raw_ocr: str, iocs: List[str]) -> VisualContent:
        """Translates diagram spatial components into a Mermaid.js flowchart and architectural narrative."""
        mermaid_code = None
        narrative = "System architecture diagram illustrating network topology and threat pathways."

        # Attempt Groq LLM conversion to Mermaid.js if API key is present
        if self.groq_client and raw_ocr:
            try:
                resp = self.groq_client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[{"role": "user", "content": DIAGRAM_MERMAID_PROMPT.format(ocr_text=raw_ocr)}],
                    max_tokens=600,
                    temperature=0.1
                )
                text = resp.choices[0].message.content or ""
                # Extract mermaid block
                match = re.search(r"```mermaid\s*([\s\S]*?)\s*```", text)
                if match:
                    mermaid_code = f"```mermaid\n{match.group(1).strip()}\n```"
                narrative_split = text.split("Narrative:")
                if len(narrative_split) > 1:
                    narrative = narrative_split[1].strip()
            except Exception:
                pass

        # Deterministic fallback Mermaid diagram if LLM was unavailable
        if not mermaid_code:
            elements = [re.sub(r'[^a-zA-Z0-9_\- ]', '', w) for w in raw_ocr.splitlines() if len(w.strip()) > 3][:4]
            if len(elements) >= 2:
                nodes = [f'    N{i}["{elem}"]' for i, elem in enumerate(elements)]
                arrows = [f'    N{i} --> N{i+1}' for i in range(len(elements) - 1)]
                mermaid_code = "```mermaid\nflowchart LR\n" + "\n".join(nodes + arrows) + "\n```"
            else:
                mermaid_code = "```mermaid\nflowchart LR\n    A[Threat Actor] -->|Inbound Vector| B[Target Network]\n```"

        structured_md = (
            f"#### 📊 Architecture / Attack Flow Diagram\n\n"
            f"{mermaid_code}\n\n"
            f"**Narrative:** {narrative}"
        )

        return VisualContent(
            visual_type=VisualType.DIAGRAM,
            raw_ocr_text=raw_ocr,
            structured_content=structured_md,
            mermaid_diagram=mermaid_code,
            extracted_iocs=iocs,
            visual_narrative=narrative
        )

    def _extract_other(self, raw_ocr: str, iocs: List[str]) -> VisualContent:
        """Fallback for presenter video feeds, logos, and non-document frames."""
        narrative = "Visual scene displaying presenter briefing or transition slide."
        structured_md = f"*(Scene Visual: {narrative})*"
        if raw_ocr:
            structured_md += f"\n> {raw_ocr}"

        return VisualContent(
            visual_type=VisualType.OTHER,
            raw_ocr_text=raw_ocr,
            structured_content=structured_md,
            extracted_iocs=iocs,
            visual_narrative=narrative
        )
