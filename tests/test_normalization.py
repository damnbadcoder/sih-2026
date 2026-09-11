"""Stage 13 — normalization tests.

Covers the deterministic text normalizer, byte-bound truncation, record
building, NDJSON serialization, and the end-to-end contract of the second
``normalized_content`` artifact (content separation, no DB persistence, and
failure cleanup).
"""

import io
import json
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.formats import MEDIA_CATEGORY_DOCUMENT, classify_format
from app.db.session import async_session_factory
from app.main import app
from app.models.artifact import Artifact
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing import runner
from app.processing.inspection import InspectionResult
from app.processing.normalization import (
    NORMALIZED_ARTIFACT_TYPE,
    _truncate_to_utf8_bytes,
    build_normalized_records,
    normalize_text,
    normalized_artifact_max_bytes,
    serialize_normalized_records,
)
from app.processing.service import ProcessingError, process_job, reserve_job_for_processing
from app.storage import StorageError, get_storage
from app.storage.local import LocalStorage

try:
    from docx import Document as _DocxDocument
except ImportError:  # pragma: no cover
    _DocxDocument = None

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    store = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


# --- fixture builders --------------------------------------------------------


def build_pdf(texts: list[str]) -> bytes:
    count = len(texts)

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def page_idx(i: int) -> int:
        return 3 + 2 * i

    def contents_idx(i: int) -> int:
        return 4 + 2 * i

    font_idx = 3 + 2 * count

    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        (
            f"2 0 obj\n<< /Type /Pages /Kids ["
            f"{' '.join(f'{page_idx(i)} 0 R' for i in range(count))}"
            f"] /Count {count} >>\nendobj\n"
        ).encode(),
    ]
    for i in range(count):
        objects.append(
            (
                f"{page_idx(i)} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {contents_idx(i)} 0 R "
                f"/Resources << /Font << /F1 {font_idx} 0 R >> >> >>\n"
                f"endobj\n"
            ).encode()
        )
    for i, text in enumerate(texts):
        content = f"BT /F1 20 Tf 72 720 Td ({esc(text)}) Tj ET\n".encode()
        objects.append(
            (
                f"{contents_idx(i)} 0 obj\n<< /Length {len(content)} >>\n"
                f"stream\n{content.decode()}"
                f"endstream\nendobj\n"
            ).encode()
        )
    objects.append(
        (
            f"{font_idx} 0 obj\n"
            f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
            f"endobj\n"
        ).encode()
    )

    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    cursor = 0
    offsets: list[int] = []
    for obj in objects:
        offsets.append(cursor)
        cursor += len(obj)
    xref_pos = len(header) + cursor
    entries = [b"0000000000 65535 f \n"]
    entries.extend(f"{off:010d} 00000 n \n".encode() for off in offsets)
    trailer = (
        f"trailer\n<< /Size {font_idx + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return header + body + f"xref\n0 {len(entries)}\n".encode() + b"".join(entries) + trailer


def build_docx(paragraphs: list[str]) -> bytes:
    document = _DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _result(
    filename: str,
    *,
    text: str | None,
    file_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> InspectionResult:
    return InspectionResult(
        input_file_id=file_id or uuid.uuid4(),
        original_filename=filename,
        media_category=MEDIA_CATEGORY_DOCUMENT,
        content_type="application/pdf",
        file_size=1,
        extension=".pdf",
        supported_for_inspection=True,
        extracted_text=text,
        metadata={} if reason is None else {"reason": reason},
    )


# --- normalize_text -----------------------------------------------------------


def test_normalize_is_idempotent():
    source = "  A\u00e9B  \r\nC\r\n\r\nD\t  "
    once = normalize_text(source)
    assert normalize_text(once) == once


def test_normalize_composes_nfc():
    assert normalize_text("Cafe\u0301\r\n\u0041\u030A\r\n") == "Café\nÅ\n"


def test_normalize_never_uses_nfkc():
    fullwidth = "ＡＢＣ ０１２"
    assert normalize_text(fullwidth) == fullwidth + "\n"


def test_normalize_converts_all_line_endings():
    assert normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd\n"


def test_normalize_strips_control_chars_but_keeps_tab_and_newline():
    assert normalize_text("a\x00b\x1f\x7fc\td\n") == "abc\td\n"


def test_normalize_trims_trailing_whitespace_per_line():
    assert normalize_text("left  \nright\t \n") == "left\nright\n"


def test_normalize_preserves_blank_lines_and_indentation():
    assert normalize_text("  para  \n\n\tdeep  \n") == "  para\n\n\tdeep\n"


def test_normalize_empty_input():
    assert normalize_text("") == ""
    assert normalize_text("\x00\x00") == ""
    assert normalize_text("   \n\n  \n") == ""


def test_normalize_always_ends_in_single_newline():
    assert normalize_text("x") == "x\n"
    assert normalize_text("x\n\n") == "x\n"


# --- truncation ---------------------------------------------------------------


def test_truncate_keeps_text_when_within_limit():
    assert _truncate_to_utf8_bytes("hello world", 100) == ("hello world", False)


def test_truncate_cuts_whole_chars_not_mid_char():
    text = "é" * 5
    prefix, truncated = _truncate_to_utf8_bytes(text, 7)  # 7 bytes: 3 whole é then partial
    assert truncated
    assert prefix == "é" * 3
    assert prefix.encode("utf-8") == text.encode("utf-8")[:6]


def test_truncate_boundary_is_inclusive():
    assert _truncate_to_utf8_bytes("é" * 4, 8) == ("é" * 4, False)


def test_truncate_zero_limit():
    assert _truncate_to_utf8_bytes("anything", 0) == ("", True)


# --- record building ----------------------------------------------------------


def test_records_are_built_in_input_order():
    a = _result("b.pdf", text="second")
    b = _result("a.pdf", text="first")
    records = build_normalized_records([b, a])
    assert [r["original_filename"] for r in records] == ["a.pdf", "b.pdf"]
    assert records[0]["normalized_text"] == "first\n"
    assert records[1]["normalized_text"] == "second\n"


def test_record_fields_for_supported_file():
    record = build_normalized_records([_result("paper.pdf", text="Hi\n")])[0]
    assert record["supported_for_inspection"] is True
    assert record["normalized_char_count"] == len("Hi\n")
    assert record["truncated"] is False
    assert record["reason"] is None
    assert set(record) == {
        "input_file_id",
        "original_filename",
        "media_category",
        "extension",
        "supported_for_inspection",
        "normalized_text",
        "normalized_char_count",
        "truncated",
        "reason",
    }


def test_record_for_unsupported_file():
    classification = classify_format("slides.pptx", _PPTX_MIME)
    file = InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename="slides.pptx",
        content_type=_PPTX_MIME,
        file_size=8,
        storage_path=f"{uuid.uuid4()}/uploads/slides.pptx",
    )
    record = build_normalized_records([InspectionResult.unsupported(file, classification)])[0]
    assert record["supported_for_inspection"] is False
    assert record["normalized_text"] is None
    assert record["normalized_char_count"] is None
    assert record["reason"] == "no inspector registered for media category"


def test_record_for_supported_but_empty_extraction():
    record = build_normalized_records([_result("scan.pdf", text=None)])[0]
    assert record["supported_for_inspection"] is True
    assert record["normalized_text"] is None
    assert record["reason"] == "no extractable text"


def test_record_flags_truncated_output():
    record = build_normalized_records(
        [_result("big.txt", text="y" * 100)], cap_bytes=10
    )[0]
    assert record["truncated"] is True
    assert len(record["normalized_text"].encode("utf-8")) <= 10


def test_record_within_cap_is_not_truncated():
    record = build_normalized_records([_result("ok.txt", text="tiny")], cap_bytes=10)[0]
    assert record["truncated"] is False
    assert record["normalized_text"] == "tiny\n"


# --- serialization ------------------------------------------------------------


async def _collect(chunks: AsyncIterator[bytes]) -> bytes:
    return b"".join([c async for c in chunks])


async def test_serializer_is_deterministic_sorted_ndjson():
    records = build_normalized_records(
        [_result("a.txt", text="one\n"), _result("b.txt", text="tw\u00e9\n")],
        cap_bytes=100,
    )
    first = await _collect(serialize_normalized_records(records))
    second = await _collect(serialize_normalized_records(records))
    assert first == second

    lines = first.splitlines()
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert list(parsed) == sorted(parsed)
    assert "é" in lines[1].decode("utf-8")


async def test_serializer_escapes_interior_newlines():
    records = build_normalized_records([_result("m.txt", text="a\nb")], cap_bytes=100)
    raw = await _collect(serialize_normalized_records(records))
    assert len(raw.splitlines()) == 1
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["normalized_text"] == "a\nb\n"


async def test_serializer_leaks_no_storage_or_absolute_paths():
    records = build_normalized_records([_result("p.pdf", text="ok")], cap_bytes=100)
    text = (await _collect(serialize_normalized_records(records))).decode("utf-8")
    assert "storage_path" not in text
    assert "stored_filename" not in text
    assert "/" not in text


def test_artifact_guard_size_scales_with_record_count():
    assert normalized_artifact_max_bytes(3) > normalized_artifact_max_bytes(1)


# --- end-to-end integration ---------------------------------------------------


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


@pytest.fixture
async def client(storage):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await cleanup_created_users()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> tuple[str, str, str]:
    email = unique_email("norm")
    CREATED_EMAILS.append(email)
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    user_id = signup.json()["id"]
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    created = await client.post("/api/v1/jobs", json={"config": {}}, headers=_auth(token))
    assert created.status_code == 201
    return user_id, token, created.json()["id"]


async def _upload(
    client: AsyncClient, token: str, job_id: str, filename, content, content_type
) -> None:
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _read_artifact_text(storage: LocalStorage, path: str) -> bytes:
    return storage.resolve(path).read_bytes()


async def _normalized_artifact_path(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(
            select(Artifact.file_path).where(
                Artifact.job_id == uuid.UUID(job_id),
                Artifact.artifact_type == NORMALIZED_ARTIFACT_TYPE,
            )
        )


async def _job_status(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def test_processing_writes_normalized_and_summary_artifacts(
    client: AsyncClient, storage: LocalStorage
):
    _, token, job_id = await _setup(client)
    marker = f"NORM_MARKER_{uuid.uuid4().hex[:8]}"
    source = f"  {marker}  \r\nBeta\t gamma\r\n\r\nLast.  "
    await _upload(client, token, job_id, "notes.txt", source.encode(), "text/plain")
    await _upload(client, token, job_id, "report.pdf", build_pdf(["PDF line"]), "application/pdf")

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        result = await process_job(uuid.UUID(job_id), db, storage)

    assert await _job_status(job_id) == "completed"

    summary = json.loads(await _read_artifact_text(storage, result.artifact_path))
    assert summary["artifact_type"] == "processing_result"
    assert marker not in json.dumps(summary)
    assert "normalized_text" not in json.dumps(summary)

    normalized_path = await _normalized_artifact_path(job_id)
    assert normalized_path is not None
    assert normalized_path != result.artifact_path
    raw = await _read_artifact_text(storage, normalized_path)
    assert marker in raw.decode("utf-8")
    records = [json.loads(line) for line in raw.splitlines()]
    assert [r["original_filename"] for r in records] == ["notes.txt", "report.pdf"]

    notes = records[0]
    assert notes["normalized_text"] == normalize_text(source)
    assert notes["normalized_char_count"] == len(normalize_text(source))
    assert notes["truncated"] is False
    assert notes["reason"] is None

    pdf = records[1]
    assert pdf["supported_for_inspection"] is True
    assert "PDF line" in pdf["normalized_text"]


async def test_normalized_content_never_reaches_database(
    client: AsyncClient, storage: LocalStorage
):
    _, token, job_id = await _setup(client)
    marker = f"NORM_MARKER_{uuid.uuid4().hex[:8]}"
    await _upload(client, token, job_id, "notes.txt", f"{marker} body\n".encode(), "text/plain")

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        await process_job(uuid.UUID(job_id), db, storage)

    async with async_session_factory() as db:
        artifacts = (
            await db.scalars(select(Artifact).where(Artifact.job_id == uuid.UUID(job_id)))
        ).all()
        assert len(artifacts) == 2
        for artifact in artifacts:
            assert marker not in (artifact.artifact_type or "")
            assert marker not in (artifact.file_path or "")
        inputs = (
            await db.scalars(select(InputFile).where(InputFile.job_id == uuid.UUID(job_id)))
        ).all()
        for input_file in inputs:
            assert marker not in (input_file.storage_path or "")
            assert marker not in (input_file.original_filename or "")
        job = await db.scalar(select(Job).where(Job.id == uuid.UUID(job_id)))
        assert marker.encode() not in (job.config or b"")

    raw = await _read_artifact_text(storage, await _normalized_artifact_path(job_id))
    assert marker in raw.decode("utf-8")


async def test_processing_unsupported_format_record_reason(
    client: AsyncClient, storage: LocalStorage
):
    _, token, job_id = await _setup(client)
    await _upload(client, token, job_id, "slides.pptx", b"fake zip", _PPTX_MIME)

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        await process_job(uuid.UUID(job_id), db, storage)

    raw = await _read_artifact_text(storage, await _normalized_artifact_path(job_id))
    records = [json.loads(line) for line in raw.splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["supported_for_inspection"] is False
    assert record["normalized_text"] is None
    assert record["reason"] == "no inspector registered for media category"


async def test_processing_docx_normalized_content(
    client: AsyncClient, storage: LocalStorage
):
    _, token, job_id = await _setup(client)
    await _upload(
        client,
        token,
        job_id,
        "memo.docx",
        build_docx(["First line", "Second line"]),
        _DOCX_MIME,
    )

    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        await process_job(uuid.UUID(job_id), db, storage)

    raw = await _read_artifact_text(storage, await _normalized_artifact_path(job_id))
    records = [json.loads(line) for line in raw.splitlines()]
    assert records[0]["normalized_text"] == "First line\nSecond line\n"


async def test_storage_failure_on_normalized_save_fails_job_and_cleans_summary(
    client: AsyncClient, storage: LocalStorage, monkeypatch
):
    class _FailNormalizedSaveStorage(LocalStorage):
        def __init__(self, base_dir):
            super().__init__(base_dir)
            self.saves = 0

        async def save(self, chunks, storage_path: str, *, max_size: int) -> int:
            self.saves += 1
            if self.saves == 2:
                async for _ in chunks:
                    pass
                raise StorageError("simulated normalized content write failure")
            return await super().save(chunks, storage_path, max_size=max_size)

    _, token, job_id = await _setup(client)
    await _upload(client, token, job_id, "a.txt", b"hello", "text/plain")

    failing = _FailNormalizedSaveStorage(storage._base_dir)
    monkeypatch.setattr(runner, "get_storage", lambda: failing)

    with pytest.raises(ProcessingError):
        async with async_session_factory() as db:
            await reserve_job_for_processing(db, uuid.UUID(job_id))
            await process_job(uuid.UUID(job_id), db, failing)

    assert await _job_status(job_id) == "failed"
    async with async_session_factory() as db:
        count = len(
            (
                await db.scalars(
                    select(Artifact).where(Artifact.job_id == uuid.UUID(job_id))
                )
            ).all()
        )
    assert count == 0