# 🛡️ Agentic AI Engine Roadmap: Automated Content Transformation

**Theme:** Cybersecurity & Intelligence Dissemination (NTRO / Defense Track)
**Core Objective:** Build a deterministic, multi-modal, agentic transformation pipeline that ingests heterogeneous raw intelligence (PDFs, CVE advisories, telemetry logs, audio/video) and orchestrates parallel generation of tailored communication artefacts without hallucinations.

---

## 1. System Architecture & Data Flow

```
[ Multi-Modal Ingestion Engine ]
├── Unstructured PDFs / DOCX  -> Docling / PyMuPDF4LLM
├── Audio / Incident Calls    -> Faster-Whisper
├── Threat Videos / Briefings -> OpenCV Keyframe Extractor + Vision LLM
└── Raw Text / CVE Feeds      -> BeautifulStoneSoup / Regex Parsers
│
▼
[ Normalization & Semantic Chunking ]
└── Unified Markdown AST + Extracted Metadata (IOCs, Timelines, CVEs)
│
▼
[ Grounding & Verification Node (LangGraph Master) ]
└── Core Fact & Context Extraction (Strict Pydantic Grounding Anchor)
│
├──────────────────────┬──────────────────────┐
▼                      ▼                      ▼
[ Agent 1: Advisory ]  [ Agent 2: Exec Brief ] [ Agent 3: Video/Story ] ...
(MITRE ATT&CK, IOCs)   (C-Level Risk & ROI)    (Scenes, Prompts, TTS)
│                      │                      │
└──────────────────────┼──────────────────────┘
▼
[ Anti-Hallucination Guard ]
(Claim Verification against Source)
│
▼
[ File Synthesis & Export ]
(python-pptx, WeasyPrint, Edge-TTS)
```

---

## 1a. Design Learnings: Why a Single `.md` File Isn't Enough

Flattening every input straight into a single narrative Markdown file is a tempting shortcut, but it introduces three concrete failure modes downstream.

### Flaw 1: Loss of High-Density Cyber/Technical Telemetry
- Structured tables, IOCs (IPs, hashes, domains), CVE mappings, and video timestamps get scrambled or dropped when flattened into pure narrative Markdown — the downstream LLM has nothing forcing it to preserve them.
- **The fix:** Emit a **Hybrid Object** — a Markdown document *plus* a structured Pydantic metadata schema, e.g. `{ text_markdown: str, extracted_iocs: list, timestamps: list, tables: list }`.

### Flaw 2: Multimodal Information Blind Spots (Video & Images)
- Transcribing video to Markdown via Whisper captures what is *said*, but misses what is *shown* — terminal output, architecture diagrams, incident slide decks.
- **The fix:** Extract keyframes (via OpenCV) and pass them through a vision model (e.g., Gemini Flash Vision) to produce visual scene descriptions alongside the audio transcript.

### Flaw 3: Multi-Agent Drift & Hallucination Risk
- If a single raw Markdown file is passed directly to every format generator alongside user parameters (tone, audience), each agent summarizes the raw context independently — e.g. the LinkedIn agent cites "500 affected systems" while the Executive Brief agent writes "several thousand."
- **The fix:** Insert an intermediate **Grounding Extraction Node** right after parsing. This node converts the normalized Markdown into a canonical, locked fact sheet (the "single source of truth") before any format-specific agent runs. This is the same role `GroundingContext` plays in Phase 2 below — the point is that it must sit immediately after normalization, not be treated as optional.

### Refined Ingestion & Normalization Flow

Rather than a single flat Markdown output, ingestion should emit a **dual-payload context bundle**:

```
[ User Upload ]
(PDF, DOCX, TXT, Audio, Video, Image)
       │
       ▼
[ Format Router (MIME Detection) ]
       ├── Text/Docs  ──► Docling / PyMuPDF4LLM  ──┐
       ├── Audio      ──► Faster-Whisper          ──┼──► [ Aggregator Node ]
       ├── Video      ──► Whisper + OpenCV Frames ──┤           │
       └── Images/OCR ──► Vision / OCR            ──┘           ▼
                                                     [ Hybrid Context Bundle ]
                                                     ├── 1. Clean Markdown (.md)
                                                     ├── 2. Structural Metadata (JSON)
                                                     └── 3. Verified Entities & IOCs
```

### Practical Library Stack for the First Pipeline

| Input Type | Tool | Notes |
| :--- | :--- | :--- |
| PDF / DOCX | `Docling` or `PyMuPDF4LLM` | Outputs Markdown with table syntax intact (`\| col \| col \|`), avoiding the table destruction common with raw `pypdf`. |
| Audio (`.mp3`, `.wav`) | `faster-whisper` | Fast local transcription with word-level timestamps. |
| Video (`.mp4`, `.mkv`) | `ffmpeg` + `opencv-python` + image captioning | Extract audio via `ffmpeg` for Whisper; sample 1 frame every 10–15 seconds; run image-captioning for visual context. |
| Regex Extractor | Deterministic regex pass | Extract IPs, CVEs, and SHA256 hashes into structured lists **before** the LLM touches the text — this needs to happen pre-LLM to guarantee zero indicator loss. |

---

## 2. Team Division (2 Engineers)

| Responsibility Area | Engineer A (Ingestion & Normalization Lead) | Engineer B (Agentic Core & Synthesis Lead) |
| :--- | :--- | :--- |
| **Primary Scope** | Multi-modal ingestion, parsing, chunking, OCR, transcription, and structural extractors. | Agent orchestration (LangGraph), prompt engineering, schema enforcement (Pydantic), hallucination checks. |
| **Deliverables** | Ingestion pipeline API, document normalizer, audio/video keyframe parser, metadata & IOC extractor. | Graph state machine, specialized artifact agents, schema validation layer, file exporters (`.pptx`, `.pdf`, `.mp3`). |
| **Hand-Off Point** | A clean, unified, validated `ExtractedSourceContext` Pydantic object containing text, tables, IOCs, and timestamped transcripts. | Consumes `ExtractedSourceContext` to execute parallel generation workers and return validated artefacts. |

---

## 3. Phase-by-Phase Roadmap

### Phase 1: Ingestion & Input Normalization (Days 1–2)

*Goal: Convert any raw, messy file into clean, standardized markdown with structured metadata.*

#### 1. Document Extraction (PDF, DOCX)
- Do not use basic `pypdf` (it loses table hierarchies and formatting).
- Use **Docling** or **PyMuPDF4LLM** to parse incoming PDFs directly into Markdown tables and clean text.
- Preserve table relationships (critical for CVE impact matrices and IOC lists).

#### 2. Audio & Video Preprocessing
- **Audio Extraction:** Run local `faster-whisper` (base or small model) to extract timestamped transcriptions.
- **Video Sampling:** Use `opencv-python` to extract 1 frame every 10–15 seconds or scene changes. Pass keyframes through a lightweight vision model (or Gemini Flash Vision) to generate visual context summaries.

#### 3. Cybersecurity-Specific Extraction Node
- Run deterministic regex extraction on the ingested text before the LLM step to collect:
  - IPv4 / IPv6 addresses
  - SHA256 / MD5 hashes
  - CVE Identifiers (`CVE-\d{4}-\d{4,7}`)
  - Domain names and URLs
- **Verification:** Ensure zero data loss of critical indicators during parsing.

---

### Phase 2: Grounding Anchor & Fact Extraction (Days 3–4)

*Goal: Prevent multi-agent drift and ensure cross-artefact consistency.*

#### 1. Context Grounding Node
- Create a primary agent whose only job is to read the raw normalized content and output an **Immutable Grounding Bundle** (`GroundingContext`).
- If an incident report says "3,200 servers compromised", this exact statistic is locked into state so Agent 1 (LinkedIn) and Agent 2 (Advisory) cannot report conflicting numbers.

#### 2. Pydantic State Definition

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class ThreatMetadata(BaseModel):
    cve_ids: List[str] = Field(default_factory=list)
    threat_actor: Optional[str] = None
    affected_systems: List[str] = Field(default_factory=list)
    severity: str = Field(description="CRITICAL, HIGH, MEDIUM, LOW")
    iocs: List[str] = Field(description="IPs, Hashes, Domains extracted directly")

class GroundingContext(BaseModel):
    title: str
    executive_overview: str
    timeline_of_events: List[str]
    technical_root_cause: str
    actionable_mitigations: List[str]
    metadata: ThreatMetadata
```

---

### Phase 3: LangGraph Agentic Pipeline Orchestration (Days 5–6)

*Goal: Construct a resilient Directed Acyclic Graph (DAG) with parallel workers.*

#### 1. State Graph Setup
- Build the pipeline using `langgraph` or native `asyncio.gather` with Instructor/Gemini.
- Set up a single graph state:

```python
from typing import TypedDict, Dict, Any, List

class TransformationState(TypedDict):
    raw_input_path: str
    input_type: str
    selected_formats: List[str]  # ["advisory", "executive_summary", "linkedin", "slides", "video_package"]
    audience: str
    tone: str
    grounding_data: GroundingContext
    artefacts: Dict[str, Any]
    validation_errors: List[str]
```

#### 2. Worker Agent Specialization

Each requested format triggers a dedicated agent node:

- **Advisory Agent:** Generates formal CERT/NTRO-style markdown with MITRE ATT&CK references, severity banners, and mitigation checklists.
- **Executive Summary Agent:** Adheres strictly to the Minto Pyramid Principle (Situation → Complication → Solution → ROI/Impact). Max 1 page.
- **Social Dissemination Agent:** Generates platform-compliant outputs (X thread capped at 280 chars per tweet; LinkedIn post with hook, whitespace, bulleted insights, and relevant hashtags).
- **Presentation Slide Agent:** Generates a structured JSON array of slides (Slide Title, 3–4 crisp bullet points, Layout Type, and detailed Speaker Notes).
- **Video Package Agent:** Generates a scene-by-scene script containing Visual Direction, Image Prompts (Midjourney/Flux-ready), Spoken Audio Narration, and timing.
- **Infographic Blueprint Agent:** Outputs layout structures (e.g., Timeline, 4-Pillar Grid, or Stat Callouts) with suggested icons and key metrics.

---

### Phase 4: Verification, Self-Correction & Export Layer (Days 7–8)

*Goal: Enforce programmatic schema validation and produce actual downloadable files.*

#### 1. Anti-Hallucination / Fact-Checker Node
- A dedicated validator node compares each generated artefact against the `GroundingContext`.
- **Validation Rule:** Does the generated artefact introduce facts, statistics, or CVEs not present in the grounding anchor?
  - If **FAIL** → Loop back to the specific generator node with error feedback.
  - If **PASS** → Route to the export synthesis layer.

#### 2. Deliverable Synthesis Tools

Do not output raw Markdown and stop there. Convert JSON schemas into tangible assets:

- **Presentation (`.pptx`):** Use `python-pptx` to build a clean corporate slide deck dynamically from the Slide Agent's JSON.
- **Executive Advisory (`.pdf`):** Use `weasyprint` or `reportlab` with pre-defined clean CSS templates (dark mode / enterprise styling).
- **Audio Voiceover (`.mp3`):** Run `edge-tts` (fast, free, high quality) on the Video Agent's narration script to produce a voiceover track.
- **Subtitles (`.srt`):** Export synchronized subtitle files based on word duration estimates.

---

## 4. Schemas & Code Contracts

### Video Storyboard Schema (`video_package.py`)

```python
from pydantic import BaseModel, Field
from typing import List

class VideoScene(BaseModel):
    scene_number: int
    duration_seconds: int
    visual_description: str = Field(description="Scene visual direction for video editor")
    ai_image_prompt: str = Field(description="Midjourney/Flux prompt to generate background")
    narration_script: str = Field(description="Exact spoken narration text")
    on_screen_text: str = Field(description="Lower-third or text overlay")

class VideoPackagePayload(BaseModel):
    title: str
    target_duration_seconds: int
    target_platform: str = Field(description="YouTube, Reels, Internal Training")
    scenes: List[VideoScene]
```

### Presentation Schema (`presentation.py`)

```python
from pydantic import BaseModel, Field
from typing import List

class Slide(BaseModel):
    slide_number: int
    layout_type: str = Field(description="TITLE, TWO_COLUMN, METRIC_HIGHLIGHT, CONCLUSION")
    title: str
    bullets: List[str] = Field(description="Max 4 concise points")
    speaker_notes: str = Field(description="Elaborate talking points for the presenter")

class PresentationPayload(BaseModel):
    deck_title: str
    presentation_objective: str
    slides: List[Slide]
```

---

## 5. Directory Structure for the AI Engine

```
ai_engine/
├── core/
│   ├── config.py              # Model configs (Gemini 1.5, Claude, Ollama)
│   ├── state.py               # LangGraph State definitions
│   └── orchestrator.py        # LangGraph Workflow graph builder
├── extractors/
│   ├── document_parser.py     # Docling / PyMuPDF integration
│   ├── media_parser.py        # Faster-Whisper audio & OpenCV video sampler
│   └── ioc_extractor.py       # Deterministic regex for CVE, IPs, Hashes
├── agents/
│   ├── grounding_agent.py     # Master context extraction agent
│   ├── advisory_agent.py      # Technical security bulletin generator
│   ├── executive_agent.py     # C-Level briefing generator
│   ├── social_agent.py        # LinkedIn / X formatters
│   ├── presentation_agent.py  # Slide JSON structure builder
│   └── video_agent.py         # Storyboard & narration script agent
├── verifiers/
│   ├── fact_checker.py        # Cross-references output with GroundingContext
│   └── schema_guard.py        # Retry loops on Pydantic validation errors
└── exporters/
    ├── pptx_builder.py        # Builds .pptx files via python-pptx
    ├── pdf_builder.py         # HTML/CSS to PDF generator via WeasyPrint
    └── tts_engine.py          # Edge-TTS voice synthesis
```
