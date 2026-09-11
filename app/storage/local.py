import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app.storage.base import DEFAULT_READ_CHUNK_BYTES, Storage, StorageError, UploadTooLargeError

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_BYTES = 1024 * 1024


class LocalStorage(Storage):
    """Stores uploads under a base directory on the local filesystem.

    The base directory is the only location the storage is allowed to write
    to. Relative ``storage_path`` keys are resolved defensively against the
    base directory and rejected when they would escape it (path traversal
    guard), so a stored path can never be leveraged to clobber arbitrary
    files on the host.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def resolve(self, storage_path: str) -> Path:
        base = self._base_dir.resolve()
        target = (base / storage_path).resolve()
        if not target.is_relative_to(base):
            raise StorageError(f"storage_path escapes upload directory: {storage_path!r}")
        return target

    async def save(
        self,
        chunks: AsyncIterator[bytes],
        storage_path: str,
        *,
        max_size: int,
    ) -> int:
        target = self.resolve(storage_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        try:
            with target.open("wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_size:
                        raise UploadTooLargeError(
                            f"upload exceeds limit of {max_size} bytes"
                        )
                    handle.write(chunk)
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                logger.warning("failed to remove partial file %s", target, exc_info=True)
            raise
        return size

    async def delete(self, storage_path: str) -> None:
        target = self.resolve(storage_path)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"could not delete stored file: {exc}") from exc

    async def read_chunks(
        self,
        storage_path: str,
        *,
        chunk_size: int = DEFAULT_READ_CHUNK_BYTES,
    ) -> AsyncIterator[bytes]:
        """Stream the stored file in ``chunk_size`` byte blocks.

        Reads the file on the event loop like the other storage operations
        (append-only short reads); each chunk yields before the next read, so
        the underlying handle is never held open longer than needed.
        """
        target = self.resolve(storage_path)
        try:
            if not target.is_file():
                raise StorageError(f"stored file missing: {storage_path}")
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(f"could not read stored file: {exc}") from exc