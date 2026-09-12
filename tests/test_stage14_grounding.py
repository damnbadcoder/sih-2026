import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete

from app.db.session import async_session_factory
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.schemas.transformation import TransformationCreateRequest
from app.services.grounding import GroundingService
from app.services.transformations import TransformationService
from app.storage.local import LocalStorage

CREATED_EMAILS: list[str] = []


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def cleanup_created_users() -> None:
    if not CREATED_EMAILS:
        return
    async with async_session_factory() as db:
        await db.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))
        await db.commit()
    CREATED_EMAILS.clear()


@pytest.fixture(autouse=True)
async def _cleanup_created():
    yield
    await cleanup_created_users()


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "uploads")


async def _make_user(prefix: str) -> User:
    email = unique_email(prefix)
    CREATED_EMAILS.append(email)
    async with async_session_factory() as db:
        user = User(email=email, password_hash="test-hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


def _payload_for(text_source: str) -> TransformationCreateRequest:
    return TransformationCreateRequest(
        title="grounding",
        outputs=[{"outputType": "advisory"}],
        sources=[{"source_type": "text", "text": text_source}],
    )


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _save_file(storage: LocalStorage, path: str, payload: bytes) -> None:
    await storage.save(_chunks(payload), path, max_size=4 * 1024)


async def test_grounding_extracts_indicators_from_text_source():
    owner = await _make_user("groundtext")
    service = TransformationService()

    text = (
        "Critical zero-day CVE-2026-1234 exploited. "
        "C2 at 203.0.113.9 and domain evil.example.com. "
        "File hash 5d41402abc4b2a76b9719d911017c592 noted."
    )
    payload = _payload_for(text)

    async with async_session_factory() as db:
        transformation = await service.create_transformation(db, owner, payload)
        context = await GroundingService().build_context(transformation)

    assert context.transformation_id == transformation.id
    assert context.ioc_extraction_available is True
    assert len(context.sources) == 1
    source = context.sources[0]
    assert source.source_type == "text"
    assert source.normalized_text is not None
    assert source.reason is None
    assert "cve" in source.iocs
    assert source.iocs["cve"] == ["CVE-2026-1234"]
    assert source.iocs["ipv4"] == ["203.0.113.9"]
    assert "evil.example.com" in source.iocs["domains"]

    assert context.indicators["cve"] == ["CVE-2026-1234"]
    assert context.indicators["ipv4"] == ["203.0.113.9"]
    assert source.metadata["ioc_total"] >= 3
    assert source.metadata["grounding_header"].startswith("====")
    assert source.metadata["chunk_count"] >= 1


async def test_grounding_unions_indicators_across_sources():
    owner = await _make_user("groundunion")
    payload = TransformationCreateRequest(
        title="grounding",
        outputs=[{"outputType": "advisory"}],
        sources=[
            {"source_type": "text", "text": "CVE-2026-0001 and 203.0.113.1"},
            {"source_type": "text", "text": "CVE-2026-0002 and 198.51.100.7"},
        ],
    )
    async with async_session_factory() as db:
        transformation = await TransformationService().create_transformation(db, owner, payload)
        context = await GroundingService().build_context(transformation)

    assert context.indicators["cve"] == ["CVE-2026-0001", "CVE-2026-0002"]
    assert context.indicators["ipv4"] == ["198.51.100.7", "203.0.113.1"]
    assert len(context.sources) == 2


async def test_grounding_url_source_records_no_fetch_policy():
    owner = await _make_user("groundurl")
    payload = TransformationCreateRequest(
        title="grounding",
        outputs=[{"outputType": "advisory"}],
        sources=[{"source_type": "url", "url": "https://example.com/report"}],
    )
    async with async_session_factory() as db:
        transformation = await TransformationService().create_transformation(db, owner, payload)
        context = await GroundingService().build_context(transformation)

    source = context.sources[0]
    assert source.source_type == "url"
    assert source.normalized_text is None
    assert source.iocs == {}
    assert source.reason == (
        "URL ingestion never fetches content; policy decision recorded"
    )
    assert source.metadata["fetch_policy"]["allowed"] is False
    assert source.metadata["fetched"] is False


async def test_grounding_file_source_inspects_stored_text_file(storage):
    owner = await _make_user("groundfile")
    async with async_session_factory() as db:
        job = Job(user_id=owner.id, status="created")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        storage_path = f"{owner.id}/{job.id}/input/incident.txt"
        await _save_file(storage, storage_path, b"IOC CVE-2026-7777 at 203.0.113.55")
        content = b"IOC CVE-2026-7777 at 203.0.113.55"

        input_file = InputFile(
            job_id=job.id,
            original_filename="incident.txt",
            stored_filename="incident.txt",
            content_type="text/plain",
            file_size=len(content),
            storage_path=storage_path,
        )
        db.add(input_file)
        await db.commit()
        await db.refresh(input_file)

        payload = TransformationCreateRequest(
            title="grounding",
            outputs=[{"outputType": "advisory"}],
            sources=[{"source_type": "file", "input_file_id": input_file.id}],
        )
        transformation = await TransformationService().create_transformation(db, owner, payload)
        context = await GroundingService(storage).build_context(transformation)

    source = context.sources[0]
    assert source.source_type == "file"
    assert source.media_category == "text"
    assert source.normalized_text is not None
    assert "CVE-2026-7777" in source.normalized_text
    assert source.iocs["cve"] == ["CVE-2026-7777"]
    assert context.indicators["cve"] == ["CVE-2026-7777"]


async def test_grounding_media_file_without_text_reports_reason(storage):
    owner = await _make_user("groundpng")
    async with async_session_factory() as db:
        job = Job(user_id=owner.id, status="created")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        storage_path = f"{owner.id}/{job.id}/input/image.png"
        png_sig = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\x0dIHDR"
            + b"\x00\x00\x02\x80"  # width 640
            + b"\x00\x00\x01\xe0"  # height 480
            + b"\x08\x06\x00\x00\x00"  # bit depth 8, truecolor, 0, 0, 0
            + b"\x00\x00\x00\x00"  # trailing CRC bytes to satisfy header window
        )
        await _save_file(storage, storage_path, png_sig)

        input_file = InputFile(
            job_id=job.id,
            original_filename="image.png",
            stored_filename="image.png",
            content_type="image/png",
            file_size=len(png_sig),
            storage_path=storage_path,
        )
        db.add(input_file)
        await db.commit()
        await db.refresh(input_file)

        payload = TransformationCreateRequest(
            title="grounding",
            outputs=[{"outputType": "advisory"}],
            sources=[{"source_type": "file", "input_file_id": input_file.id}],
        )
        transformation = await TransformationService().create_transformation(db, owner, payload)
        context = await GroundingService(storage).build_context(transformation)

    source = context.sources[0]
    assert source.source_type == "file"
    assert source.media_category == "image"
    assert source.normalized_text is None
    assert source.iocs == {}
    assert source.reason == "no extractable text"
    assert context.indicators["cve"] == []