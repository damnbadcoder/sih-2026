# Multimodal Ingestion & Intelligence Pipelines

A unified, production-ready multimodal intelligence engine designed for cybersecurity threat intelligence, vulnerability triage, and digital forensics.

This package ingests heterogeneous inputs across **four distinct modalities**—**Text/Documents**, **Images**, **Audio**, and **Video**—and normalizes them into a dual-payload contract:
1. **Deterministic Structured JSON**: Machine-readable context with verified IOCs, timestamps, bounding boxes, and citations ready for vector storage, database persistence, and LangGraph multi-agent reasoning.
2. **Clean Grounded Markdown**: Formatted report with footnote-style citations, provenance tables, and Minto Pyramid structured analysis ready for human analyst UI rendering.

---

## Table of Contents
1. [Prerequisites & Environment Variables](#prerequisites--environment-variables)
2. [Package Architecture & Exports](#package-architecture--exports)
3. [FastAPI Integration Guide](#fastapi-integration-guide)
   - [Recommended Project Structure](#recommended-project-structure)
   - [Asynchronous Execution Best Practice](#asynchronous-execution-best-practice)
   - [Complete FastAPI Router Implementation](#complete-fastapi-router-implementation)
4. [Input & Output Reference](#input--output-reference)
5. [CLI & Testing](#cli--testing)
6. [How the Pipelines Work Behind the Scenes](#how-the-pipelines-work-behind-the-scenes)
   - [Text Pipeline](#1-text-pipeline-pipelinestext_pipeline)
   - [Image Pipeline](#2-image-pipeline-pipelinesimage_pipeline)
   - [Audio Pipeline](#3-audio-pipeline-pipelinesaudio_pipeline)
   - [Video Pipeline](#4-video-pipeline-pipelinesvideo_pipeline)

---

## Prerequisites & Environment Variables

Make sure the following system packages and Python dependencies are installed:

```bash
# Ubuntu / Debian system packages
sudo apt update && sudo apt install -y ffmpeg tesseract-ocr
```

Create or configure your `.env` file in the project root:

```env
# Groq API Key (Used by Text and Video pipelines for semantic enrichment)
GROQ_API_KEY=gsk_...

# Gemini API Key (Used by Image and Audio pipelines for multimodal grounding)
GEMINI_API_KEY=AIzaSy...
```

---

## Package Architecture & Exports

All pipelines inherit from the abstract base class [`BasePipeline`](./base.py) (`from pipelines.base import BasePipeline`), exposing a uniform `.process()` method and procedural helper functions.

Import everything directly from the root `pipelines` package:

```python
from pipelines import (
    # Pipeline Classes
    TextPipeline,
    ImagePipeline,
    AudioPipeline,
    VideoPipeline,

    # Procedural Helper Functions
    ingest_text,
    ingest_image,
    ingest_audio,
    ingest_video,

    # Result Schemas & Dataclasses
    EnrichedGroundingContext,
    ExtractedSourceContext,
    ImagePipelineResult,
    AudioPipelineResult,
    VideoEnrichedGroundingContext,
    ExtractedVideoContext,
)
```

---

## FastAPI Integration Guide

### Recommended Project Structure

```text
backend/
├── main.py                     # FastAPI application factory
├── routers/
│   └── ingestion.py            # Multimodal ingestion endpoints
├── pipelines/                  # This pipelines package
└── storage/                    # Output directory for persisted artifacts
```

### Asynchronous Execution Best Practice

The pipelines perform compute-heavy operations (OCR, Whisper speech-to-text, OpenCV frame parsing) and network I/O (Gemini API, Groq API).

> **IMPORTANT FOR FASTAPI**: Always run pipeline calls in a worker thread using `asyncio.to_thread` or pass them to FastAPI `BackgroundTasks`. Never run `.process()` directly on the main event loop, or you will block concurrent HTTP requests.

---

### Complete FastAPI Router Implementation

Here is a complete, copy-paste-ready FastAPI router (`routers/ingestion.py`) demonstrating file uploads, byte processing, non-blocking execution, and dual-payload responses:

```python
import asyncio
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse

from pipelines import (
    TextPipeline,
    ImagePipeline,
    AudioPipeline,
    VideoPipeline,
    ingest_text,
    ingest_image,
    ingest_audio,
    ingest_video,
)

router = APIRouter(prefix="/api/v1/ingest", tags=["Multimodal Ingestion"])

# Initialize reusable pipeline instances
text_pipe = TextPipeline()
image_pipe = ImagePipeline()
audio_pipe = AudioPipeline()
video_pipe = VideoPipeline()

OUTPUT_DIR = Path("ingestion_outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# 1. TEXT / DOCUMENT INGESTION (PDF, DOCX, MD, TXT, LOG, CSV, JSON)
# =====================================================================
@router.post("/text")
async def ingest_document_endpoint(
    file: UploadFile = File(..., description="Document file (PDF, DOCX, MD, TXT, LOG, CSV, JSON)"),
    enrich: bool = Form(True, description="Enable Groq LLM semantic reasoning and Minto Pyramid structure"),
):
    """
    Ingests documents, extracts tables and IOCs, OCRs embedded images,
    and produces grounded JSON and Markdown.
    """
    try:
        content = await file.read()
        filename = file.filename or "uploaded_document"

        # Execute off the main event loop
        result, md_path, json_path = await asyncio.to_thread(
            text_pipe.process,
            input_data=content,
            filename=filename,
            enrich=enrich,
            output_dir=OUTPUT_DIR,
        )

        return {
            "status": "success",
            "modality": "text",
            "filename": filename,
            "markdown_payload": getattr(result, "markdown_payload", ""),
            "structured_data": result.model_dump(),
            "artifacts": {
                "markdown_file": str(md_path) if md_path else None,
                "json_file": str(json_path) if json_path else None,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Text ingestion failed: {str(exc)}")


# =====================================================================
# 2. IMAGE INGESTION (PNG, JPG, JPEG, WEBP)
# =====================================================================
@router.post("/image")
async def ingest_image_endpoint(
    file: UploadFile = File(..., description="Diagram, screenshot, or forensic image"),
    force_mock: bool = Form(False, description="Force deterministic offline mock result"),
):
    """
    Ingests technical diagrams and architecture captures, extracts visual
    semantic grounding anchors, and formats citation footnotes.
    """
    try:
        content = await file.read()
        filename = file.filename or "uploaded_image.jpg"

        result = await asyncio.to_thread(
            image_pipe.process,
            image_input=content,
            image_name=filename,
            force_mock=force_mock,
            out_dir=OUTPUT_DIR,
        )

        return {
            "status": "success",
            "modality": "image",
            "title": result.title,
            "mode": result.mode,
            "model": result.model,
            "grounding_score": result.grounding_score,
            "anchors_count": len(result.anchors),
            "markdown_payload": result.markdown_output,
            "structured_data": asdict(result),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image ingestion failed: {str(exc)}")


# =====================================================================
# 3. AUDIO INGESTION (WAV, MP3, M4A, OGG, FLAC)
# =====================================================================
@router.post("/audio")
async def ingest_audio_endpoint(
    file: UploadFile = File(..., description="Audio recording, wiretap, or incident triage call"),
    force_mock: bool = Form(False, description="Force deterministic offline mock result"),
):
    """
    Ingests audio streams, extracts speaker attributions and timecode citations,
    and classifies threat indicators into grounded markdown.
    """
    try:
        content = await file.read()
        filename = file.filename or "uploaded_audio.wav"

        result = await asyncio.to_thread(
            audio_pipe.process,
            audio_input=content,
            audio_name=filename,
            force_mock=force_mock,
            out_dir=OUTPUT_DIR,
        )

        return {
            "status": "success",
            "modality": "audio",
            "title": result.title,
            "mode": result.mode,
            "model": result.model,
            "grounding_score": result.grounding_score,
            "temporal_anchors_count": len(result.anchors),
            "markdown_payload": result.markdown_output,
            "structured_data": asdict(result),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audio ingestion failed: {str(exc)}")


# =====================================================================
# 4. VIDEO INGESTION (MP4, MKV, AVI, MOV)
# =====================================================================
@router.post("/video")
async def ingest_video_endpoint(
    file: UploadFile = File(..., description="Video briefing, screencast, or terminal capture"),
    enrich: bool = Form(True, description="Enable Groq LLM cross-modal temporal/visual alignment"),
):
    """
    Decomposes video into scenes, transcribes speech with Whisper, OCRs keyframes,
    aligns audio and visual streams, and extracts timeline intelligence.
    """
    temp_video_path = None
    try:
        # Video decoding requires file on disk for OpenCV/FFmpeg
        suffix = Path(file.filename or "temp_video.mp4").suffix or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            temp_video_path = Path(tmp.name)

        result, md_path, json_path = await asyncio.to_thread(
            video_pipe.process,
            video_path=temp_video_path,
            enrich=enrich,
            output_dir=OUTPUT_DIR,
        )

        return {
            "status": "success",
            "modality": "video",
            "filename": file.filename,
            "markdown_payload": getattr(result, "markdown_payload", ""),
            "structured_data": result.model_dump(),
            "artifacts": {
                "markdown_file": str(md_path) if md_path else None,
                "json_file": str(json_path) if json_path else None,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video ingestion failed: {str(exc)}")
    finally:
        # Clean up temporary uploaded video file
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
```

---

## Input & Output Reference

### Input Types Accepted

| Pipeline | In-Memory `bytes` | `str` / `Path` on Disk | Key Optional Parameters |
| :--- | :---: | :---: | :--- |
| **Text** | ✅ Yes | ✅ Yes | `enrich=True/False`, `filename="doc.pdf"`, `output_dir=Path` |
| **Image** | ✅ Yes | ✅ Yes | `image_name="arch.png"`, `force_mock=False`, `out_dir=Path` |
| **Audio** | ✅ Yes | ✅ Yes | `audio_name="call.wav"`, `force_mock=False`, `out_dir=Path` |
| **Video** | ⚠️ Via temp file | ✅ Yes | `enrich=True/False`, `output_dir=Path` |

### Returned Objects & Output Serialization

1. **Text Pipeline**:
   - Returns tuple: `(result, markdown_path, json_path)`
   - `result` is an instance of `EnrichedGroundingContext` (when `enrich=True`) or `ExtractedSourceContext` (when `enrich=False`).
   - Call `result.model_dump()` for Python dictionary / JSON serialization.
   - Access `result.markdown_payload` for the clean formatted Markdown string.

2. **Image Pipeline**:
   - Returns `ImagePipelineResult` dataclass.
   - Call `dataclasses.asdict(result)` for JSON serialization.
   - Fields: `title`, `metadata`, `anchors` (bounding boxes, extracted text, semantic categories), `entities`, `markdown_output`, `grounding_score`, `mode`.

3. **Audio Pipeline**:
   - Returns `AudioPipelineResult` dataclass.
   - Call `dataclasses.asdict(result)` for JSON serialization.
   - Fields: `title`, `metadata`, `anchors` (speaker, timestamp range, verbatim quote, threat category), `entities`, `markdown_output`, `grounding_score`, `mode`.

4. **Video Pipeline**:
   - Returns tuple: `(result, markdown_path, json_path)`
   - `result` is an instance of `VideoEnrichedGroundingContext` (when `enrich=True`) or `ExtractedVideoContext` (when `enrich=False`).
   - Call `result.model_dump()` for Python dictionary / JSON serialization.
   - Fields: `metadata`, `scenes` (aligned audio transcript + visual OCR + keyframe timestamps), `extracted_iocs`, `minto_pyramid`, `markdown_payload`.

---

## CLI & Testing

You can test any pipeline individually via the CLI from the repo root:

```bash
# 1. Text Pipeline CLI
python -m pipelines.text_pipeline.ingest --input sample_cve_report.pdf --enrich

# 2. Image Pipeline CLI
python -m pipelines.image_pipeline.cli --input diagram.png

# 3. Audio Pipeline CLI
python -m pipelines.audio_pipeline.cli --input call.wav

# 4. Video Pipeline CLI
python -m pipelines.video_pipeline.ingest --input briefing.mp4 --enrich

# Run complete test suite (16 tests across all 4 pipelines)
python -m unittest discover -s pipelines -t . -p "test_*.py" -v
```

---

## How the Pipelines Work Behind the Scenes

### 1. Text Pipeline (`pipelines/text_pipeline/`)

```
Raw Document (PDF/DOCX/MD/TXT)
  │
  ├─► Phase 1: Deterministic Parsing
  │     ├── Structural table extraction (Markdown grid / CSV / JSON)
  │     ├── Regex IOC extraction (IPv4/6, CVE, hashes, URLs, domains)
  │     └── Embedded Figure/Diagram OCR via Tesseract
  │
  ├─► Phase 2: Semantic Reasoning & Minto Pyramid Synthesis
  │     └── Groq LLM (e.g. Qwen 2.5 32B / GPT-OSS 120B / LLaMA 3.3 70B)
  │           ├── Governing Thought & Key Incident Drivers
  │           ├── Explanatory Evidence & Grounded Context
  │           └── Downstream LangGraph Agent Directives
  │
  └─► Automatic Cleanup: Phase 1 intermediate files are deleted immediately.
```

- **Embedded Image Handling & OCR**: When processing PDFs or DOCX files, the parser extracts embedded figures, diagrams, and architecture screenshots to an in-memory buffer and runs Tesseract OCR to ensure visual text is not lost.
- **Table Preservation**: Structural tables (e.g. affected software matrices, CVSS scores) are extracted into structured `TableData` objects rather than flattened into unparseable prose.
- **Deterministic IOC Extraction**: High-precision regex rules extract IPv4, IPv6, MD5, SHA-256, CVEs, MITRE ATT&CK techniques, URLs, and domains without LLM hallucination.
- **Semantic Minto Pyramid Enrichment**: In Phase 2, the document is synthesized using the Minto Pyramid Principle (Governing Thought, Key Incident Drivers, Explanatory Evidence, Downstream Agent Directives).
- **Zero Disk Residue**: Temporary intermediate files generated between Phase 1 and Phase 2 are automatically deleted once the enriched JSON and Markdown are written.

---

### 2. Image Pipeline (`pipelines/image_pipeline/`)

```
Forensic Image / Architecture Diagram
  │
  ├─► ImagePreprocessor
  │     └── EXIF orientation correction, RGB normalization, dimension extraction
  │
  ├─► Vision Interpreter Cascade
  │     ├── Primary:   gemini-2.5-flash-lite
  │     ├── Secondary: gemini-3.5-flash-lite
  │     └── Tertiary:  gemini-2.0-flash
  │     └── Fallback:  Deterministic Offline Mock Engine (zero downtime)
  │
  └─► Grounding Citation Formatter
        ├── Visual semantic anchors with normalized 2D bounding boxes [ymin, xmin, ymax, xmax]
        ├── Footnote citations ([^img-1], [^img-2]) linking narrative to visual elements
        └── Provenance Grounding Table with verbatim labels and confidence scores
```

- **Preprocessing**: Handles format normalization, EXIF orientation correction, and metadata extraction (dimensions, color channels, file size).
- **Gemini Vision Cascade**: Uses structured prompts with JSON schema constraints to extract verbatim diagram text and 2D bounding boxes (`[ymin, xmin, ymax, xmax]`).
- **Resilient Fallback**: If the API key is missing or quotas are exceeded, the engine gracefully falls back to deterministic mock grounding anchors so backend services never crash.
- **Grounding Footnotes**: Synthesizes a formal advisory where every entity references its visual anchor (e.g., `[^img-1]`) mapped to a Provenance Grounding Table.

---

### 3. Audio Pipeline (`pipelines/audio_pipeline/`)

```
Audio Recording / Wiretap / Triage Call (WAV/MP3/M4A)
  │
  ├─► AudioPreprocessor & Metadata Extractor
  │     └── Header inspection, sample rate, channels, PCM duration calculation
  │
  ├─► Multimodal Audio Interpreter Cascade
  │     ├── Primary:   gemini-2.5-flash-lite (direct audio context)
  │     ├── Secondary: gemini-3.5-flash-lite
  │     └── Fallback:  Deterministic Offline Mock Engine
  │
  └─► Temporal Citation Formatter
        ├── Speaker diarization & chronological timeline reconstruction
        ├── Verbatim quote extraction & Threat Classification (e.g. INCIDENT_ALERT)
        └── Footnote citations ([^aud-1]) linked to Provenance & Audio Grounding Table
```

- **Audio Validation**: Inspects headers, extracts sample rates, duration, and channel topology without external dependencies for PCM WAV files.
- **Gemini Audio Reasoning**: Processes full acoustic context to perform speaker diarization, transcribe verbatim utterances, and categorize segments into incident types (`INCIDENT_ALERT`, `COMMAND_LINE`, `LATERAL_MOVEMENT`, etc.).
- **Temporal Citations**: Anchors each threat statement to an exact timecode (e.g., `[^aud-1] (00:00 - 00:04) Speaker 1`).
- **Offline Resilience**: Automatically falls back to deterministic mock threat triage data if the external API is unreachable.

---

### 4. Video Pipeline (`pipelines/video_pipeline/`)

```
Video Stream (MP4/MKV/AVI)
  │
  ├──► Visual Channel: Scene Boundary Detection (OpenCV)
  │      ├── Color histogram delta & optical scene transitions
  │      ├── Representative keyframe extraction (Slide, Diagram, Terminal, Presenter)
  │      └── Tesseract OCR on on-screen text, commands, and code blocks
  │
  ├──► Audio Channel: Audio Demuxing & Transcription
  │      ├── FFmpeg stream demuxing to high-fidelity audio buffer
  │      └── OpenAI Whisper speech-to-text with word/segment timestamps
  │
  ├──► Cross-Modal Temporal Alignment
  │      └── Merges visual OCR keyframes and spoken transcripts based on timecodes
  │
  ├──► Semantic Groq Enrichment
  │      └── Synthesizes multi-scene timeline, Minto Pyramid, and unified IOC list
  │
  └─► Lifecycle Cleanup
         └── Intermediate audio WAV tracks and scene frame dumps are auto-deleted
```

- **Intelligent Scene Decomposition**: Uses OpenCV color histogram delta analysis to detect transitions between slides, architecture diagrams, terminal screencasts, and presenter cameras.
- **Dual-Channel Processing**: Concurrently processes visual video frames (OCR, visual classification) and the demuxed audio channel (Whisper speech-to-text with start/end timecodes).
- **Cross-Modal Synchronization**: Intersects spoken narrative with on-screen visual artifacts based on timestamp overlaps (e.g., matching a spoken CVE mention with on-screen terminal exploit code).
- **Semantic Groq Enrichment**: Groq's high-throughput LLM organizes the multi-scene timeline into actionable incident intelligence and threat actor attribution.
- **Lifecycle Cleanup**: Extracted temporary `.wav` audio tracks and scene frames are scrubbed from disk upon completion.
