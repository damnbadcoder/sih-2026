# 🎙️ Audio Ingestion & Temporal Grounding Pipeline

## Overview
The `audio_pipeline` processes recorded incident triage calls, conference briefings, wiretaps, and intelligence intercepts. It performs temporal and speaker grounding using Gemini Multimodal Audio models (`gemini-2.5-flash-lite`), mapping verbatim spoken speech to timecodes and speaker roles with inline citations (`[^aud-X]`).

---

## Architecture & Workflow

```
[Input Audio (.wav, .mp3, .m4a, .ogg)]
       │
       ├──► 1. Preprocessor (Inspect sample rate, channels, duration, normalize WAV/MP3)
       │
       ├──► 2. Multimodal Audio Grounding (Gemini Audio / gemini-2.5-flash-lite)
       │         ├──► Verbatim speech transcription with timecodes ('00:15 - 00:42')
       │         ├──► Speaker role attribution ('Incident Commander', 'SOC Lead')
       │         ├──► Category triage (INCIDENT_ALERT, THREAT_ACTOR, IOC_DISCLOSURE)
       │         └──► Inline temporal citation synthesis ([^aud-1], [^aud-2], ...)
       │
       └──► 3. Output Synthesis (AudioPipelineResult)
                 ├──► Markdown report with inline citations & audio grounding table
                 ├──► Structured Pydantic JSON contract (Anchors, Entities, Provenance)
                 └──► Automatic mock fallback for offline resilience
```

---

## Directory Structure
```
pipelines/audio_pipeline/
├── schema.py                      # Pydantic data contracts (AudioPipelineResult, AudioGroundingAnchor, AudioProvenance)
├── ingest.py                      # Master AudioPipeline engine & procedural ingest_audio
├── cli.py                         # Standalone CLI interface
├── extractor.py                   # High-level extraction wrapper
├── formatter.py                   # Markdown report generator with audio grounding tables
├── mock.py                        # Deterministic offline mock engine
├── types.py                       # Entity types and enums
├── extractors/
│   ├── preprocessor.py            # Audio loader, MIME detection, and duration calculation
│   └── metadata_extractor.py      # WAV sample rate, channel, and width inspector
├── interpreters/
│   ├── gemini_client.py           # Google GenAI Gemini audio client with model fallback
│   ├── interpreter.py             # AudioVisionInterpreter orchestrator
│   ├── parser.py                  # Structured response parser
│   └── prompts.py                 # Grounding prompts & system instructions
└── tests/
    ├── test_audio_pipeline.py     # Unit test suite
    └── samples/sample.wav         # Reference incident triage audio sample
```

---

## Quickstart & CLI Usage

### 1. CLI Processing
```bash
python -m pipelines.audio_pipeline.cli --input sample.wav --output-dir outputs/
```

### 2. Python SDK
```python
from pipelines.audio_pipeline import AudioPipeline, ingest_audio

pipeline = AudioPipeline()
result = pipeline.process("sample.wav")

print(f"Title: {result.title}")
print(f"Extracted {len(result.anchors)} temporal grounding anchors")
print(result.markdown_output)
```
