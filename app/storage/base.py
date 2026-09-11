from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol


class StorageError(Exception):
    """Base error for storage failures."""


class UploadTooLargeError(StorageError):
    """Raised while streaming an upload that exceeds the configured limit."""


DEFAULT_READ_CHUNK_BYTES = 64 * 1024


class Storage(Protocol):
    """Abstraction over the physical location of uploaded source files.

    Implementations write uploads incrementally (never buffering the whole
    file in memory) and own the mapping between the relative ``storage_path``
    keys stored in the database and the underlying location.
    """

    async def save(
        self,
        chunks: AsyncIterator[bytes],
        storage_path: str,
        *,
        max_size: int,
    ) -> int:
        """Stream ``chunks`` to ``storage_path``; return bytes written.

        Aborts with :class:`UploadTooLargeError` as soon as ``max_size`` is
        exceeded and guarantees no partial file is left behind on any failure.
        """
        ...

    async def delete(self, storage_path: str) -> None:
        """Remove the file at ``storage_path``; missing files are a no-op."""
        ...

    def resolve(self, storage_path: str) -> Path:
        """Map a relative ``storage_path`` to an absolute filesystem path."""
        ...

    def read_chunks(
        self,
        storage_path: str,
        *,
        chunk_size: int = DEFAULT_READ_CHUNK_BYTES,
    ) -> AsyncIterator[bytes]:
        """Stream the stored file as bounded chunks.

        Missing files raise :class:`StorageError`. The default byte chunk
        size is small enough for inspectors to bound their memory use while
        streaming arbitrarily large source files.
        """
        ...