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
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing.inspection import (
    DOCXInspector,
    InspectionError,
    PDFInspector,
    get_inspector,
)
from app.processing.service import (
    ProcessingError,
    process_job,
    reserve_job_for_processing,
)
from app.storage import StorageError, get_storage
from app.storage.local import LocalStorage

try:
    from docx import Document as _DocxDocument
except ImportError:  # pragma: no cover
    _DocxDocument = None


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    store = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


# --- fixture builders --------------------------------------------------------


def build_pdf(texts: list[str]) -> bytes:
    """Hand-craft a minimal, spec-valid PDF that pypdf can parse.

    Layout: object 1 = catalog, 2 = pages, then one (page, contents) pair per
    page starting at 3, and finally the font object. Byte offsets are computed
    so the xref table is exact.
    """
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


async def _bytes_chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


def make_input_file(filename: str, content_type: str, data: bytes) -> InputFile:
    return InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename=filename,
        stored_filename=f"stored_{filename}",
        content_type=content_type,
        file_size=len(data),
        storage_path=f"{uuid.uuid4()}/job/{filename}",
    )


async def write_via_storage(storage: LocalStorage, input_file: InputFile, data: bytes) -> None:
    await storage.save(
        _bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1
    )


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# --- format-aware inspector selection ----------------------------------------


def test_selection_resolves_pdf_via_format_class():
    inspector = get_inspector(classify_format("paper.pdf", "application/pdf"))
    assert isinstance(inspector, PDFInspector)


def test_selection_resolves_docx_via_format_class():
    inspector = get_inspector(classify_format("article.docx", _DOCX_MIME))
    assert isinstance(inspector, DOCXInspector)


def test_selection_routes_documents_to_distinct_inspectors():
    pdf = classify_format("a.pdf", "application/pdf")
    docx = classify_format("b.docx", _DOCX_MIME)
    assert get_inspector(pdf) is not get_inspector(docx)


def test_selection_unsupported_categories_are_none():
    classifications = [
        classify_format("slides.pptx", _PPTX_MIME),
        classify_format("blob.xyz", "application/octet-stream"),
    ]
    for classification in classifications:
        assert get_inspector(classification) is None


def test_selection_resolves_new_supported_formats():
    from app.processing.inspection.audio import AudioInspector
    from app.processing.inspection.image import ImageInspector
    from app.processing.inspection.spreadsheet import XLSXInspector
    from app.processing.inspection.video import VideoInspector

    sheet = classify_format(
        "data.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert isinstance(get_inspector(sheet), XLSXInspector)
    assert isinstance(get_inspector(classify_format("pic.png", "image/png")), ImageInspector)
    assert isinstance(get_inspector(classify_format("song.mp3", "audio/mpeg")), AudioInspector)
    assert isinstance(get_inspector(classify_format("clip.mp4", "video/mp4")), VideoInspector)


def test_selection_coarse_document_category_remains_ambiguous():
    assert get_inspector(MEDIA_CATEGORY_DOCUMENT) is None


# --- local storage streaming reads --------------------------------------------


async def test_read_chunks_streams_exact_content(storage: LocalStorage):
    data = b"chunky payload " * 1000
    path = "readme.txt"
    await storage.save(_bytes_chunks(data), path, max_size=len(data) + 1)

    chunks: list[bytes] = [c async for c in storage.read_chunks(path)]

    assert b"".join(chunks) == data


async def test_read_chunks_respects_chunk_size(storage: LocalStorage):
    data = b"0123456789abcdef" * 4
    path = "binned.txt"
    await storage.save(_bytes_chunks(data), path, max_size=len(data) + 1)

    sizes = [len(c) async for c in storage.read_chunks(path, chunk_size=8)]

    assert sizes[:3] == [8, 8, 8]
    assert sum(sizes) == len(data)


async def test_read_chunks_missing_file_raises_storage_error(storage: LocalStorage):
    with pytest.raises(StorageError):
        async for _ in storage.read_chunks("ghost.bin"):
            pass


# --- PDF inspection ------------------------------------------------------------


async def test_pdf_inspection_extracts_pages(storage: LocalStorage):
    data = build_pdf(["Page one", "Page two"])
    input_file = make_input_file("paper.pdf", "application/pdf", data)
    await write_via_storage(storage, input_file, data)

    result = await PDFInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_DOCUMENT
    assert result.metadata["page_count"] == 2
    assert result.extracted_text is not None
    assert "Page one" in result.extracted_text
    assert "Page two" in result.extracted_text
    assert result.metadata["char_count"] > 0


async def test_pdf_inspection_no_text_still_supported(storage: LocalStorage):
    data = build_pdf(["", ""])
    input_file = make_input_file("scan.pdf", "application/pdf", data)
    await write_via_storage(storage, input_file, data)

    result = await PDFInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.metadata["page_count"] == 2
    assert result.extracted_text is None


async def test_pdf_inspection_malformed_raises_inspection_error(storage: LocalStorage):
    data = b"%PDF-1.4 not really a pdf"
    input_file = make_input_file("broken.pdf", "application/pdf", data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await PDFInspector().inspect(input_file, storage)


async def test_pdf_inspection_missing_file_raises_inspection_error(storage: LocalStorage):
    input_file = make_input_file("ghost.pdf", "application/pdf", b"x")

    with pytest.raises(InspectionError):
        await PDFInspector().inspect(input_file, storage)


# --- DOCX inspection ------------------------------------------------------------


@pytest.mark.skipif(_DocxDocument is None, reason="python-docx not installed")
async def test_docx_inspection_extracts_paragraphs(storage: LocalStorage):
    data = build_docx(["First line", "Second line"])
    input_file = make_input_file("article.docx", _DOCX_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await DOCXInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_DOCUMENT
    assert result.metadata["paragraph_count"] == 2
    assert result.extracted_text == "First line\nSecond line"


@pytest.mark.skipif(_DocxDocument is None, reason="python-docx not installed")
async def test_docx_inspection_blank_body_has_no_text(storage: LocalStorage):
    data = build_docx([])
    input_file = make_input_file("blank.docx", _DOCX_MIME, data)
    await write_via_storage(storage, input_file, data)

    result = await DOCXInspector().inspect(input_file, storage)

    assert result.supported_for_inspection is True
    assert result.metadata["paragraph_count"] == 0
    assert result.extracted_text is None


async def test_docx_inspection_malformed_raises_inspection_error(storage: LocalStorage):
    data = b"this is not a zip"
    input_file = make_input_file("broken.docx", _DOCX_MIME, data)
    await write_via_storage(storage, input_file, data)

    with pytest.raises(InspectionError):
        await DOCXInspector().inspect(input_file, storage)


async def test_docx_inspection_size_mismatch_raises_inspection_error(storage: LocalStorage):
    input_file = make_input_file("fake.docx", _DOCX_MIME, b"x" * 20)
    await write_via_storage(storage, input_file, b"short")

    with pytest.raises(InspectionError):
        await DOCXInspector().inspect(input_file, storage)


# --- processing-service integration -------------------------------------------


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


async def _signup_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    user_id = signup.json()["id"]
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


async def _create_job(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/v1/jobs", json={"config": {}}, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(
    client: AsyncClient, token: str, job_id: str, filename: str, content: bytes, content_type: str
) -> None:
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201


async def _job_status(job_id: str) -> str:
    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def _reserve_and_process(job_id: str, storage: LocalStorage):
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        return await process_job(uuid.UUID(job_id), db, storage)


async def _read_artifact(storage: LocalStorage, artifact_path: str) -> dict:
    return json.loads(storage.resolve(artifact_path).read_text())


async def test_processing_pdf_completes_with_summary(client: AsyncClient, storage: LocalStorage):
    email = unique_email("doc_pdf")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "paper.pdf", build_pdf(["Hello PDF"]), "application/pdf")

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    artifact = await _read_artifact(storage, result.artifact_path)
    entry = artifact["inspected_files"][0]
    assert entry["original_filename"] == "paper.pdf"
    assert entry["media_category"] == MEDIA_CATEGORY_DOCUMENT
    assert entry["supported_for_inspection"] is True
    assert entry["metadata"] == {"page_count": 1, "char_count": len("Hello PDF")}


async def test_processing_docx_completes_with_summary(client: AsyncClient, storage: LocalStorage):
    email = unique_email("doc_docx")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "memo.docx", build_docx(["First", "Second"]), _DOCX_MIME)

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    artifact = await _read_artifact(storage, result.artifact_path)
    entry = artifact["inspected_files"][0]
    assert entry["original_filename"] == "memo.docx"
    assert entry["supported_for_inspection"] is True
    assert entry["metadata"] == {"paragraph_count": 2, "char_count": 12}


async def test_processing_malformed_pdf_fails_job(client: AsyncClient, storage: LocalStorage):
    email = unique_email("doc_badpdf")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "broken.pdf", b"%PDF-1.4 fake", "application/pdf")

    with pytest.raises(ProcessingError):
        await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "failed"


async def test_processing_malformed_docx_fails_job(client: AsyncClient, storage: LocalStorage):
    email = unique_email("doc_baddocx")
    CREATED_EMAILS.append(email)
    _, token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, "broken.docx", b"not a zip", _DOCX_MIME)

    with pytest.raises(ProcessingError):
        await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "failed"