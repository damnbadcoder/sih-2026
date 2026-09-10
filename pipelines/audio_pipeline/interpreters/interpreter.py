"""
Gemini Audio Interpreter for speech transcription and temporal grounding.
"""
from typing import Optional, Tuple
from .gemini_client import GeminiAudioClient
from .parser import AudioResponseParser
from .prompts import AUDIO_SYSTEM_INSTRUCTION, build_audio_prompt


class AudioVisionInterpreter:
    """Interprets voice and audio feeds using Gemini Multimodal Audio."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = GeminiAudioClient(api_key=api_key, model=model)

    @property
    def is_available(self) -> bool:
        return self.client.is_available

    def interpret(
        self,
        audio_bytes: bytes,
        audio_name: str,
        mime_type: str,
        duration_seconds: Optional[float] = None,
    ) -> Tuple[dict, list, any, str]:
        """
        Executes Gemini audio inference and returns structured anchors and entities.
        Returns: (parsed_dict, anchors, entities, model_used)
        """
        duration_str = f"{duration_seconds:.1f}s" if duration_seconds else "Unknown"
        prompt = build_audio_prompt(audio_name=audio_name, duration_str=duration_str)

        raw_text, used_model = self.client.generate_audio_content(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            prompt=prompt,
            system_instruction=AUDIO_SYSTEM_INSTRUCTION,
        )
        parsed_data, anchors, entities = AudioResponseParser.parse_payload(raw_text)
        return parsed_data, anchors, entities, used_model
