"""
Audio preprocessor: format detection, byte normalization, and duration heuristics.
"""
import io
import mimetypes
import wave
from pathlib import Path
from typing import Tuple, Union, Optional


class AudioPreprocessor:
    """Prepares and validates audio buffers for Gemini multimodal ingestion."""

    MIME_MAP = {
        ".wav": "audio/wav",
        ".mp3": "audio/mp3",
        ".m4a": "audio/m4a",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
    }

    @classmethod
    def load_and_preprocess(
        cls,
        audio_input: Union[str, Path, bytes],
        default_name: str = "recording.wav",
    ) -> Tuple[bytes, str, str, float, Optional[float]]:
        """
        Loads audio, detects MIME type, calculates size and duration.
        Returns: (raw_bytes, audio_name, mime_type, file_size_kb, duration_seconds)
        """
        if isinstance(audio_input, (str, Path)):
            path = Path(audio_input)
            raw_bytes = path.read_bytes()
            audio_name = path.name
            suffix = path.suffix.lower()
            mime_type = cls.MIME_MAP.get(suffix) or mimetypes.guess_type(path.name)[0] or "audio/wav"
        elif isinstance(audio_input, bytes):
            raw_bytes = audio_input
            audio_name = default_name
            mime_type = "audio/wav"
        else:
            raise ValueError(f"Unsupported audio input type: {type(audio_input)}")

        file_size_kb = round(len(raw_bytes) / 1024.0, 2)
        duration_seconds = cls._estimate_duration(raw_bytes, mime_type)

        return raw_bytes, audio_name, mime_type, file_size_kb, duration_seconds

    @staticmethod
    def _estimate_duration(raw_bytes: bytes, mime_type: str) -> Optional[float]:
        """Attempts to read duration from audio headers using built-in libraries or ffprobe."""
        if "wav" in mime_type:
            try:
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        return round(frames / float(rate), 2)
            except Exception:
                pass

        # Fallback for MP3, M4A, OGG, FLAC via ffprobe if available
        try:
            import subprocess
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", "-"],
                input=raw_bytes,
                capture_output=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                return round(float(res.stdout.strip()), 2)
        except Exception:
            pass

        return None
