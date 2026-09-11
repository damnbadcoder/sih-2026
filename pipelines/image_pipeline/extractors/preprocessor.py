"""
Image preprocessor: normalization, scaling, resolution analysis, and format conversion.
"""
import io
from pathlib import Path
from typing import Tuple, Union
from PIL import Image


class ImagePreprocessor:
    """Handles image tensor conversion and dimension safety."""

    MAX_DIMENSION = 2048

    @classmethod
    def load_and_preprocess(
        cls,
        image_input: Union[str, Path, bytes],
        default_name: str = "uploaded_diagram.jpg",
    ) -> Tuple[bytes, str, float, Tuple[int, int]]:
        """
        Loads an image, normalizes color space, calculates dimensions and size,
        and returns (processed_jpeg_bytes, image_name, file_size_kb, resolution).
        """
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            raw_bytes = path.read_bytes()
            image_name = path.name
        elif isinstance(image_input, bytes):
            raw_bytes = image_input
            image_name = default_name
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        file_size_kb = len(raw_bytes) / 1024.0

        pil_img = Image.open(io.BytesIO(raw_bytes))
        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")

        orig_w, orig_h = pil_img.size

        # Safe proportional scaling if image exceeds max dimensions
        if max(orig_w, orig_h) > cls.MAX_DIMENSION:
            scale = cls.MAX_DIMENSION / float(max(orig_w, orig_h))
            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_buffer = io.BytesIO()
        pil_img.save(out_buffer, format="JPEG", quality=95)
        processed_bytes = out_buffer.getvalue()

        return processed_bytes, image_name, round(file_size_kb, 2), pil_img.size
