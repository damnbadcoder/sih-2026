# 🎙️ Audio Pipeline

## Purpose & Scope
The `audio_pipeline` processes spoken audio sources such as recorded emergency response bridge calls, threat intelligence podcasts, and voice debriefs.

## Planned Capabilities (Roadmap)
1. **Local Transcription:** Uses `faster-whisper` (base or small model) for fast local speech-to-text with word-level timestamps.
2. **Speaker Identification:** Optional diarization to separate incident commanders, threat researchers, and operators.
3. **IOC Audio Recovery:** Normalization of spoken technical indicators (e.g., "one ninety two dot one sixty eight" -> "192.168").
4. **Structured Output:** Emits timestamped text segments and passes transcribed text to the deterministic IOC extractor and grounding engine.
