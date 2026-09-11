import pytest

from app.storage import StorageError, UploadTooLargeError
from app.storage.local import LocalStorage


async def _chunks(*parts: bytes):
    for part in parts:
        if part:
            yield part


def _any_files(root):
    return any(p.is_file() for p in root.rglob("*"))


async def test_save_streams_chunks_and_returns_size(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    size = await storage.save(
        _chunks(b"hello ", b"world", b"!"), "u1/j1/input/file.pdf", max_size=100
    )
    assert size == 12
    target = storage.resolve("u1/j1/input/file.pdf")
    assert target.read_bytes() == b"hello world!"


async def test_save_creates_parent_directories(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    await storage.save(_chunks(b"x"), "a/b/c/f.txt", max_size=100)
    assert (tmp_path / "uploads" / "a/b/c/f.txt").is_file()


async def test_save_rejects_oversized_upload_and_removes_partial(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(UploadTooLargeError):
        await storage.save(
            _chunks(b"12345", b"67890", b"11111"), "u/j/f.txt", max_size=12
        )
    assert not (tmp_path / "uploads" / "u/j/f.txt").exists()
    assert not _any_files(tmp_path / "uploads")


def test_resolve_maps_relative_path_inside_base(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    resolved = storage.resolve("u/j/input/f.txt")
    assert resolved.is_relative_to(tmp_path / "uploads")
    assert resolved == (tmp_path / "uploads" / "u/j/input/f.txt").resolve()


def test_resolve_rejects_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(StorageError):
        storage.resolve("../../../etc/passwd")


async def test_save_with_traversal_storage_path_writes_nothing(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(StorageError):
        await storage.save(_chunks(b"x"), "../../../etc/passwd", max_size=100)
    assert not (tmp_path / "etc").exists()
    assert not _any_files(tmp_path / "uploads")


def test_storage_never_escapes_base_via_encoded_dots(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(StorageError):
        storage.resolve("u/j/input/../../../../../tmp/evil")
    assert not (tmp_path / "tmp").exists()


async def test_delete_removes_file(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    await storage.save(_chunks(b"data"), "u/j/f.txt", max_size=100)
    await storage.delete("u/j/f.txt")
    assert not (tmp_path / "uploads" / "u/j/f.txt").exists()


async def test_delete_missing_file_is_noop(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    await storage.delete("u/j/does-not-exist.txt")


async def test_delete_rejects_traversal_path(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(StorageError):
        await storage.delete("../../etc/passwd")