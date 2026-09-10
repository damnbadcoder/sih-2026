"""
Audio extraction and speech-to-text transcription module for video pipelines.
Uses ffmpeg to demux audio and Groq Whisper (whisper-large-v3) for timestamped segments.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

from pipelines.video_pipeline.schema import AudioSegment

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


class VideoAudioExtractor:
    """Extracts audio track from video files and produces timestamped transcription segments."""

    def __init__(self, groq_api_key: Optional[str] = None):
        self.api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.api_key) if (GROQ_AVAILABLE and self.api_key) else None

    def extract_audio(self, video_path: str, output_audio_path: Optional[str] = None) -> Optional[str]:
        """
        Uses ffmpeg to extract a 16kHz mono audio track from a video.

        Args:
            video_path: Path to video file (.mp4, .mkv, .avi, etc.).
            output_audio_path: Optional destination path for .wav file.

        Returns:
            Path to extracted audio file, or None if extraction fails or no audio track exists.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_audio_path is None:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(temp_fd)
            output_audio_path = temp_path

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path)
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 1000:
                return output_audio_path
            return None
        except (subprocess.CalledProcessError, FileNotFoundError):
            # No audio track or ffmpeg execution failed
            if os.path.exists(output_audio_path):
                try:
                    os.unlink(output_audio_path)
                except OSError:
                    pass
            return None

    def transcribe(self, audio_path: str) -> Tuple[str, List[AudioSegment]]:
        """
        Transcribes audio using Groq Whisper API (whisper-large-v3) with timestamped segments.

        Args:
            audio_path: Path to WAV/MP3 audio file.

        Returns:
            Tuple of (full_transcript_text, list_of_AudioSegments).
        """
        if not audio_path or not os.path.exists(audio_path):
            return "", []

        if not self.groq_client:
            print("[!] Note: Groq Whisper client not initialized (missing API key or offline).", flush=True)
            return "", []

        try:
            with open(audio_path, "rb") as f:
                transcription = self.groq_client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    temperature=0.0
                )

            full_text = transcription.text if hasattr(transcription, "text") else ""
            segments: List[AudioSegment] = []

            raw_segments = getattr(transcription, "segments", [])
            for idx, seg in enumerate(raw_segments, start=1):
                start = float(seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0))
                end = float(seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0))
                txt = (seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip()

                if txt:
                    segments.append(AudioSegment(
                        segment_id=idx,
                        start_seconds=round(start, 2),
                        end_seconds=round(end, 2),
                        text=txt
                    ))

            return full_text, segments
        except Exception as err:
            print(f"[!] Warning: Whisper transcription encountered error: {err}", flush=True)
            return "", []
