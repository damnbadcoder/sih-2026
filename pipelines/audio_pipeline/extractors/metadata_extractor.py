"""
Audio metadata inspection utilities.
"""
from typing import Dict, Any, Optional
import io
import wave


class AudioMetadataExtractor:
    """Extracts technical audio stream properties without external binaries."""

    @staticmethod
    def inspect(raw_bytes: bytes) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "channels": 1,
            "sample_rate_hz": None,
            "sample_width_bytes": None,
        }
        try:
            with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                info["channels"] = wf.getnchannels()
                info["sample_rate_hz"] = wf.getframerate()
                info["sample_width_bytes"] = wf.getsampwidth()
        except Exception:
            pass
        return info
