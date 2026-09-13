from typing import Any
from mutagen import File as MutagenFile
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, stream_to_buffer
from app.storage import Storage


class AudioInspector(BaseInspector):
    media_category = "audio"
    supported_extensions = frozenset({".mp3", ".wav"})
    supported_mime_types = frozenset({"audio/mpeg", "audio/wav", "audio/x-wav"})

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        buffer = await stream_to_buffer(file, storage)
        try:
            audio = MutagenFile(buffer)
            metadata: dict[str, Any] = {
                "duration_seconds": 0.0,
                "bitrate": 0,
                "sample_rate": 0,
                "channels": 0,
                "tags": {},
            }

            if audio is not None and audio.info is not None:
                metadata["duration_seconds"] = float(getattr(audio.info, "length", 0.0))
                metadata["bitrate"] = int(getattr(audio.info, "bitrate", 0))
                metadata["sample_rate"] = int(getattr(audio.info, "sample_rate", 0))
                metadata["channels"] = int(getattr(audio.info, "channels", 0))

            if audio is not None and audio.tags:
                metadata["tags"] = {str(k): str(v) for k, v in audio.tags.items()}

            summary_text = (
                f"Audio Asset ({file.original_filename}): "
                f"Duration={metadata['duration_seconds']:.2f}s, "
                f"Bitrate={metadata['bitrate']}bps, "
                f"Channels={metadata['channels']}"
            )

            return summary_text, metadata
        finally:
            buffer.close()