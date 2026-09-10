"""
Gemini Vision Interpreter for diagram grounding.
"""
from typing import Optional, Tuple
from .gemini_client import GeminiVisionClient
from .parser import ResponseParser
from .prompts import SYSTEM_INSTRUCTION, build_extraction_prompt


class ImageVisionInterpreter:
    """Interprets diagram image tensors using Gemini Vision models."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = GeminiVisionClient(api_key=api_key, model=model)

    @property
    def is_available(self) -> bool:
        return self.client.is_available

    def interpret(
        self,
        image_bytes: bytes,
        image_name: str,
        resolution: Tuple[int, int],
    ) -> Tuple[dict, list, any, str]:
        """
        Executes Gemini Vision generation and parses the structured response.
        Returns: (parsed_dict, anchors, entities, model_used)
        """
        prompt = build_extraction_prompt(image_name=image_name, resolution=resolution)
        raw_text, used_model = self.client.generate_vision_content(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        parsed_data, anchors, entities = ResponseParser.parse_payload(raw_text)
        return parsed_data, anchors, entities, used_model
