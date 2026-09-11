import logging
from typing import Any

from app.config import get_settings
from app.core.formats import MEDIA_CATEGORY_TEXT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError
from app.storage import Storage, StorageError

logger = logging.getLogger(__name__)

_READ_CHUNK_BYTES = 64 * 1024


class TextInspector(BaseInspector):
    """Plain-text inspector: safe UTF-8 decode with graceful fallbacks."""

    media_category = MEDIA_CATEGORY_TEXT
    supported_extensions = frozenset({".txt"})
    supported_mime_types = frozenset({"text/plain"})

    def __init__(self, max_text_bytes: int | None = None) -> None:
        self._max_text_bytes = max_text_bytes

    def _max_bytes(self) -> int:
        if self._max_text_bytes is not None:
            return self._max_text_bytes
        return get_settings().MAX_UPLOAD_SIZE_BYTES

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        data, truncated = await _read_bounded(file, storage, self._max_bytes())
        text = _decode_text(data)
        return text, {"truncated": truncated, "char_count": len(text)}


async def _read_bounded(
    file: InputFile, storage: Storage, limit: int
) -> tuple[bytes, bool]:
    """Stream up to ``limit`` bytes from ``storage``; report if cut off."""
    data = bytearray()
    truncated = False
    try:
        async for chunk in storage.read_chunks(
            file.storage_path, chunk_size=_READ_CHUNK_BYTES
        ):
            remaining = limit - len(data)
            if len(chunk) > remaining:
                if remaining > 0:
                    data.extend(chunk[:remaining])
                truncated = True
                break
            data.extend(chunk)
    except StorageError as exc:
        raise InspectionError(
            f"stored input file could not be read: {file.storage_path}"
        ) from exc
    if not truncated and len(data) != file.file_size:
        raise InspectionError(f"stored input file size mismatch: {file.storage_path}")
    return bytes(data), truncated


def _decode_text(data: bytes) -> str:
    """Decode as UTF-8, tolerating a BOM and invalid byte sequences.

    Un-decodable bytes are replaced so a malformed file never crashes the
    worker; the caller can still inspect the recovered text.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")