"""
Gemini client wrapper with automatic model fallback cascade and resilience.
"""
import os
from typing import Optional, List, Tuple
from dotenv import load_dotenv

load_dotenv()


class GeminiVisionClient:
    """Manages authentication and model execution for Gemini multimodal requests."""

    PRIMARY_MODEL = "gemini-2.5-flash-lite"
    FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-2.0-flash"]

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.preferred_model = model or self.PRIMARY_MODEL

    @property
    def is_available(self) -> bool:
        """Returns True if a valid API key is present."""
        return bool(self.api_key and not self.api_key.startswith("YOUR_") and len(self.api_key) >= 10)

    def generate_vision_content(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        system_instruction: str,
    ) -> Tuple[str, str]:
        """
        Executes generation against Gemini with fallback cascade across available models.
        Returns: Tuple of (response_text, model_used).
        """
        if not self.is_available:
            raise ValueError("GEMINI_API_KEY is not set or invalid.")

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        models_to_try: List[str] = [self.preferred_model] + [
            m for m in self.FALLBACK_MODELS if m != self.preferred_model
        ]

        last_error = None
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=[image_part, prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                if response and response.text:
                    return response.text.strip(), m
            except Exception as e:
                last_error = e
                err_msg = str(e).lower()
                # If model is 404/deprecated, proceed to fallback model in cascade
                if "404" in err_msg or "not found" in err_msg or "no longer available" in err_msg:
                    continue
                else:
                    raise e

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")
