# 🎥 Video Ingestion & Multimodal Intelligence Pipeline

## Overview
The `video_pipeline` processes technical cybersecurity briefings, recorded incident response calls, vulnerability proof-of-concept demos, and terminal screencasts. It extracts synchronized audio speech, non-uniform scene keyframes, visual OCR, architecture diagrams, and indicators of compromise (IOCs), synthesizing them into an aligned multimodal intelligence contract.

---

## Architecture & Workflow

```
[Input Video (.mp4/.mkv/.avi)]
       │
       ├──► 1. Audio Demuxing (ffmpeg @ 16kHz mono)
       │         └──► Groq Whisper (whisper-large-v3) ──► Timestamped Speech Segments
       │
       ├──► 2. Non-Uniform Scene Detection (PySceneDetect ContentDetector)
       │         └──► Keyframe Settling + Perceptual Hash Deduplication (pHash)
       │
       ├──► 3. Visual Classification & Triage
       │         ├──► SLIDE: Structured OCR Headings & Bullets
       │         ├──► TERMINAL: Monospace Code Blocks & Regex Path/IOC Extraction
       │         ├──► DIAGRAM: Mermaid.js Flowchart & Architectural Flow
       │         └──► OTHER: Scene Narrative Description
       │
       └──► 4. Temporal Multimodal Alignment
                 └──► Merges keyframe visuals with overlapping speech [T_start, T_end]
                           │
                           ├──► Phase 1 Hand-Off: {name}_video_context.md & .json
                           │
                           └──► Phase 2 Semantic Grounding: Groq LLM Enrichment
                                     └──► Dual-Payload: Enriched Markdown & JSON Contract
                                     └──► Automatic cleanup of temporary intermediate files
```

---

## Directory Structure
```
pipelines/video_pipeline/
├── schema.py                      # Pydantic data contract (ExtractedVideoContext, AlignedScene, etc.)
├── ingest.py                      # Unified CLI and programmatic pipeline engine
├── video_ingestion_pipeline.py    # Public API export alias
├── extractors/
│   ├── audio_extractor.py         # ffmpeg demuxing + Groq Whisper transcription
│   ├── scene_detector.py          # PySceneDetect + pHash perceptual deduplication
│   ├── visual_classifier.py       # Heuristic & brightness triage (SLIDE/TERMINAL/DIAGRAM/OTHER)
│   ├── specialized_extractors.py  # Slide/Terminal/Diagram/IOC visual content extractors
│   └── temporal_aligner.py        # Pairs visual keyframes with spoken intervals
└── tests/
    ├── test_video_ingestion.py    # Unit & integration test suite
    └── samples/                   # Synthetic threat briefing video samples
```

---

## Quickstart & CLI Usage

### 1. Basic Ingestion (Aligned Markdown + JSON)
```bash
python -m pipelines.video_pipeline.ingest --input /path/to/threat_briefing.mp4 --output-dir outputs/
```

### 2. Full Semantic Grounding & Enrichment (with Intermediate Cleanup)
```bash
python -m pipelines.video_pipeline.ingest --input /path/to/threat_briefing.mp4 --enrich --output-dir outputs/
```

### 3. Programmatic Usage in Python
```python
from pipelines.video_pipeline import VideoIngestionPipeline

pipeline = VideoIngestionPipeline(output_dir="outputs")

# Raw aligned multimodal context
context = pipeline.process_video("briefing.mp4")
print(f"Extracted {len(context.scenes)} scenes and {len(context.iocs.cves)} CVEs")

# Full semantic grounding with Groq LLM
source_ctx, enriched_ctx = pipeline.process_and_enrich("briefing.mp4", save_outputs=True)
print(enriched_ctx.to_markdown())
```

---

## Verification & Testing
Run the test suite:
```bash
.venv/bin/python -m unittest -v pipelines/video_pipeline/tests/test_video_ingestion.py
```
