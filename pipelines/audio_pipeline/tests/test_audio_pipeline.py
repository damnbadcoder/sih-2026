"""
Unit tests for audio preprocessing, mock extraction, and pipeline execution.
"""
import io
import math
import struct
import wave
from pipelines.audio_pipeline.ingest import AudioPipeline, ingest_audio
from pipelines.audio_pipeline.extractors.preprocessor import AudioPreprocessor
from pipelines.audio_pipeline.extractors.metadata_extractor import AudioMetadataExtractor
from pipelines.audio_pipeline.mock import get_mock_audio_pipeline_result


def create_synthetic_wav(duration_s: float = 1.0, freq: float = 440.0, rate: int = 16000) -> bytes:
    """Generates a valid PCM 16-bit mono WAV buffer in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        n_frames = int(duration_s * rate)
        data = bytearray()
        for i in range(n_frames):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * (i / rate)))
            data.extend(struct.pack("<h", val))
        wf.writeframes(data)
    return buf.getvalue()


def test_audio_preprocessor():
    wav_bytes = create_synthetic_wav(duration_s=1.5)
    raw, name, mime, size_kb, duration = AudioPreprocessor.load_and_preprocess(wav_bytes, default_name="test.wav")
    assert len(raw) > 0
    assert mime == "audio/wav"
    assert size_kb > 0
    assert duration is not None
    assert 1.4 <= duration <= 1.6


def test_audio_metadata_extractor():
    wav_bytes = create_synthetic_wav()
    meta = AudioMetadataExtractor.inspect(wav_bytes)
    assert meta["channels"] == 1
    assert meta["sample_rate_hz"] == 16000
    assert meta["sample_width_bytes"] == 2


def test_audio_mock_result():
    res = get_mock_audio_pipeline_result(audio_name="incident_bridge.wav")
    assert res.metadata.source_audio_name == "incident_bridge.wav"
    assert len(res.grounding_sources) >= 5
    assert "Incident Triage Call" in res.markdown_output
    assert "Provenance & Audio Grounding Table" in res.markdown_output
    assert "[^aud-1]" in res.markdown_output
    assert res.mode == "mock"


def test_audio_pipeline_fallback():
    wav_bytes = create_synthetic_wav()
    pipeline = AudioPipeline()
    res = pipeline.process(wav_bytes, audio_name="synth.wav", force_mock=True)
    assert res.mode == "mock"
    assert res.metadata.source_audio_name == "synth.wav"
    assert len(res.grounding_sources) >= 5


import unittest


class TestAudioPipeline(unittest.TestCase):
    def test_audio_preprocessor_case(self):
        test_audio_preprocessor()

    def test_audio_metadata_extractor_case(self):
        test_audio_metadata_extractor()

    def test_audio_mock_result_case(self):
        test_audio_mock_result()

    def test_audio_pipeline_fallback_case(self):
        test_audio_pipeline_fallback()


if __name__ == "__main__":
    unittest.main()
