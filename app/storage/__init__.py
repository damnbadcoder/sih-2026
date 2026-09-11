from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.storage.base import Storage, StorageError, UploadTooLargeError
from app.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    """Dependency: returns the application's configured local storage."""
    return LocalStorage(Path(get_settings().UPLOAD_DIR))


__all__ = ["Storage", "StorageError", "UploadTooLargeError", "LocalStorage", "get_storage"]