# 🖼️ Image Ingestion & Visual Semantic Grounding Pipeline

## Overview
The `image_pipeline` ingests cybersecurity architecture diagrams, threat infographics, and visual incident evidence. It performs semantic visual grounding using Gemini Vision models (`gemini-2.5-flash-lite`), replacing raw numerical 2D bounding boxes with visual provenance anchors and inline citations (`[^src-X]`).

---

## Architecture & Workflow

```
[Input Image (.jpg, .png, .webp)]
       │
       ├──► 1. Preprocessor (Resolution, format normalization, size optimization)
       │
       ├──► 2. Semantic Visual Grounding (Gemini Vision / gemini-2.5-flash-lite)
       │         ├──► Verbatim text extraction mapped to visual positions ('Top-Left', 'Central Hub')
       │         ├──► Category triage (CORE_CONCEPT, BENEFIT, VULNERABILITY, THREAT_ACTOR)
       │         └──► Inline citation synthesis ([^src-1], [^src-2], ...)
       │
       └──► 3. Output Synthesis (PipelineResult)
                 ├──► Markdown report with inline citations & visual provenance table
                 ├──► Structured Pydantic JSON contract (Anchors, Entities, Provenance)
                 └──► Automatic mock fallback for offline resilience
```

---

## Directory Structure
```
pipelines/image_pipeline/
├── schema.py                      # Pydantic data contracts (PipelineResult, GroundingAnchor, ImageProvenance)
├── ingest.py                      # Master ImagePipeline engine & procedural ingest_image
├── cli.py                         # Standalone CLI interface
├── extractor.py                   # High-level extraction wrapper
├── formatter.py                   # Markdown report generator with provenance tables
├── mock.py                        # Deterministic offline mock engine
├── types.py                       # Entity types and enums
├── extractors/
│   ├── preprocessor.py            # Image loader, resize, and byte preprocessor
│   └── ocr_utils.py               # Local OCR fallback utilities
├── interpreters/
│   ├── gemini_client.py           # Google GenAI Gemini vision client with model fallback
│   ├── interpreter.py             # ImageVisionInterpreter orchestrator
│   ├── parser.py                  # Structured response parser
│   └── prompts.py                 # Grounding prompts & system instructions
└── tests/
    ├── test_image_pipeline.py     # Unit test suite
    └── samples/test.jpg           # Reference cybersecurity diagram sample
```

---

## Quickstart & CLI Usage

### 1. CLI Processing
```bash
python -m pipelines.image_pipeline.cli --input test.jpg --output-dir outputs/
```

### 2. Python SDK
```python
from pipelines.image_pipeline import ImagePipeline, ingest_image

pipeline = ImagePipeline()
result = pipeline.process("test.jpg")

print(f"Title: {result.title}")
print(f"Extracted {len(result.anchors)} visual grounding anchors")
print(result.markdown_output)
```
