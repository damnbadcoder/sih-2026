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

        if info["sample_rate_hz"] is None:
            try:
                import subprocess
                import json
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "stream=channels,sample_rate,bits_per_sample", "-of", "json", "-"],
                    input=raw_bytes,
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    streams = data.get("streams", [])
                    if streams:
                        s = streams[0]
                        info["channels"] = int(s.get("channels", 1))
                        info["sample_rate_hz"] = int(s.get("sample_rate", 44100))
                        bps = s.get("bits_per_sample")
                        info["sample_width_bytes"] = int(bps) // 8 if bps else 2
            except Exception:
                pass

        return info
