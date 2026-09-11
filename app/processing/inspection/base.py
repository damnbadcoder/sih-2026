import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol

from app.core.formats import MEDIA_CATEGORY_UNKNOWN, FormatClass
from app.models.input_file import InputFile
from app.storage import Storage, StorageError

_SPOOL_ROLLOVER_BYTES = 1024 * 1024


class InspectionError(Exception):
    """Raised when a stored input file cannot be inspected safely.

    The message never includes absolute filesystem paths; ``storage_path``
    values are relative keys owned by the storage abstraction.
    """


@dataclass(frozen=True)
class InspectionResult:
    """Normalized metadata produced by inspecting a single input file.

    Internal to the processing layer; extracted text lives only on this object
    and in the worker's memory, never in the database or in artifacts.
    """

    input_file_id: uuid.UUID
    original_filename: str
    media_category: str
    content_type: str | None
    file_size: int
    extension: str | None
    supported_for_inspection: bool
    extracted_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unsupported(cls, file: InputFile, classification: FormatClass) -> "InspectionResult":
        return cls(
            input_file_id=file.id,
            original_filename=file.original_filename,
            media_category=classification.media_category,
            content_type=classification.mime_type,
            file_size=file.file_size,
            extension=classification.extension,
            supported_for_inspection=False,
            metadata={"reason": "no inspector registered for media category"},
        )


class ContentInspector(Protocol):
    """Interface every future (PDF/DOCX/image/audio/video) inspector implements."""

    media_category: str
    supported_extensions: frozenset[str]
    supported_mime_types: frozenset[str]

    async def inspect(self, file: InputFile, storage: Storage) -> InspectionResult:
        """Inspect ``file`` through ``storage`` and return normalized metadata."""
        ...


class BaseInspector:
    """Reads stored files only through the storage abstraction.

    Subclasses declare :attr:`media_category` (used for coarse routing) plus
    :attr:`supported_extensions` / :attr:`supported_mime_types` (used for
    precise format-aware selection) and override :meth:`_extract`. The stored
    bytes are reached via ``storage.read_chunks``, never through
    client-supplied paths or absolute filesystem locations.
    """

    media_category: str = MEDIA_CATEGORY_UNKNOWN
    supported_extensions: frozenset[str] = frozenset()
    supported_mime_types: frozenset[str] = frozenset()

    async def inspect(self, file: InputFile, storage: Storage) -> InspectionResult:
        text, metadata = await self._extract(file, storage)
        return InspectionResult(
            input_file_id=file.id,
            original_filename=file.original_filename,
            media_category=self.media_category,
            content_type=file.content_type,
            file_size=file.file_size,
            extension=PurePosixPath(file.original_filename).suffix.lower() or None,
            supported_for_inspection=True,
            extracted_text=text,
            metadata=metadata,
        )

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        return None, {}


async def stream_to_buffer(file: InputFile, storage: Storage) -> Any:
    """Stream ``file`` into a seekable buffer that spills to disk past 1 MiB.

    Formats such as PDF/DOCX need random access to the whole file, so the
    full source is materialized here — but into a memory-bounded spool, never
    a single in-memory blob. Size equality with the recorded ``file_size`` is
    verified; a missing or mis-sized file becomes a controlled
    :class:`InspectionError`.
    """
    buffer = tempfile.SpooledTemporaryFile(max_size=_SPOOL_ROLLOVER_BYTES, mode="w+b")  # noqa: SIM115
    total = 0
    try:
        async for chunk in storage.read_chunks(file.storage_path):
            buffer.write(chunk)
            total += len(chunk)
    except StorageError as exc:
        buffer.close()
        raise InspectionError(
            f"stored input file could not be read: {file.storage_path}"
        ) from exc
    if total != file.file_size:
        buffer.close()
        raise InspectionError(f"stored input file size mismatch: {file.storage_path}")
    buffer.seek(0)
    return buffer