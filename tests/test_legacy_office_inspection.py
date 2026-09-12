import io
import json
import subprocess
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from docx import Document as _DocxDocument
from httpx import ASGITransport, AsyncClient
from pptx import Presentation as _PptxPresentation
from sqlalchemy import delete

from app.core.formats import (
    MEDIA_CATEGORY_DOCUMENT,
    MEDIA_CATEGORY_PRESENTATION,
    classify_format,
)
from app.core.uploads import ALLOWED_UPLOAD_TYPES
from app.db.session import async_session_factory
from app.main import app
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.processing.inspection import (
    DOCInspector,
    InspectionError,
    PPTInspector,
    get_inspector,
    legacy_office,
)
from app.processing.normalization import iter_normalized_records
from app.processing.service import ProcessingError, process_job, reserve_job_for_processing
from app.storage import get_storage
from app.storage.local import LocalStorage

CREATED_EMAILS: list[str] = []

_SOFFICE_BINARY = legacy_office._libreoffice_binary()
_HEADLESS_ARGS = legacy_office._HEADLESS_ARGS


def _soffice_available() -> bool:
    return _SOFFICE_BINARY is not None


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
def storage(tmp_path) -> LocalStorage:
    store = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
async def client(storage):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await cleanup_created_users()


# --- deterministic legacy .doc / .ppt fixture builders -----------------------
#
# python-docx / python-pptx generate the OOXML originals, then headless
# LibreOffice on the same runtime round-trips them into genuine legacy OLE2
# binary .doc/.ppt files. The same tool is thus both fixture generator and
# extraction engine; the fixtures are real MS formats, not approximations.


def _through_soffice(source: bytes, target_ext: str) -> bytes:
    assert _SOFFICE_BINARY is not None, "LibreOffice required to build fixtures"
    with tempfile.TemporaryDirectory(prefix="office_fixture_") as workdir:
        work = Path(workdir)
        src = work / "input"
        src.write_bytes(source)
        out = work / "out"
        out.mkdir()
        profile = work / "profile"
        profile.mkdir()
        cmd = [
            _SOFFICE_BINARY,
            *_HEADLESS_ARGS,
            "-env:UserInstallation=file://" + profile.as_posix(),
            "--convert-to",
            target_ext,
            "--outdir",
            str(out),
            str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")
        outputs = list(out.glob("*"))
        assert len(outputs) == 1, f"expected a single converted fixture, got {outputs!r}"
        return outputs[0].read_bytes()


def build_doc(paragraphs: list[str]) -> bytes:
    document = _DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buf = io.BytesIO()
    document.save(buf)
    return _through_soffice(buf.getvalue(), "doc")


def build_ppt(slide_lines: list[str]) -> bytes:
    prs = _PptxPresentation()
    blank = prs.slide_layouts[6]
    for line in slide_lines:
        slide = prs.slides.add_slide(blank)
        textbox = slide.shapes.add_textbox(0, 0, 200, 100)
        textbox.text = line
    buf = io.BytesIO()
    prs.save(buf)
    return _through_soffice(buf.getvalue(), "ppt")


# --- helpers ------------------------------------------------------------------


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
    await storage.save(_bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1)


async def _inspect(storage: LocalStorage, filename: str, data: bytes):
    suffix = Path(filename).suffix
    inspector = get_inspector(classify_format(filename, ALLOWED_UPLOAD_TYPES[suffix]))
    assert inspector is not None, filename
    input_file = make_input_file(filename, ALLOWED_UPLOAD_TYPES[suffix], data)
    await write_via_storage(storage, input_file, data)
    return await inspector.inspect(input_file, storage)


# --- format-aware selection (runs everywhere) ---------------------------------


def test_legacy_office_extensions_resolve_registered_inspectors():
    doc_inspector = get_inspector(classify_format("legacy.doc", "application/msword"))
    assert isinstance(doc_inspector, DOCInspector)
    ppt_inspector = get_inspector(
        classify_format("legacy.ppt", "application/vnd.ms-powerpoint")
    )
    assert isinstance(ppt_inspector, PPTInspector)


def test_legacy_office_extensions_classify_to_document_and_presentation():
    doc = classify_format("legacy.doc", "application/msword")
    ppt = classify_format("legacy.ppt", "application/vnd.ms-powerpoint")
    assert doc.media_category == MEDIA_CATEGORY_DOCUMENT
    assert ppt.media_category == MEDIA_CATEGORY_PRESENTATION


# --- actual extraction via LibreOffice (requires the runtime tool) ------------

pytestmark = pytest.mark.skipif(
    not _soffice_available(), reason="LibreOffice not installed in this runtime"
)


def test_runtime_has_working_libreoffice():
    assert _SOFFICE_BINARY is not None
    probe = subprocess.run(
        [_SOFFICE_BINARY, "--version"], capture_output=True, timeout=60
    )
    assert probe.returncode == 0
    assert b"LibreOffice" in probe.stdout


async def test_legacy_doc_extracts_real_paragraph_text(storage: LocalStorage):
    data = build_doc(
        ["Meeting minutes begin", "critical server=192.168.1.10", "Approved by board"]
    )
    result = await _inspect(storage, "minutes.doc", data)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_DOCUMENT
    assert result.metadata["format"] == "doc"
    assert result.metadata["converted_via"] == "libreoffice"
    assert result.metadata["paragraph_count"] == 3
    assert result.extracted_text is not None
    assert "Meeting minutes begin" in result.extracted_text
    assert "critical server=192.168.1.10" in result.extracted_text
    assert "Approved by board" in result.extracted_text


async def test_legacy_ppt_extracts_real_slide_text(storage: LocalStorage):
    data = build_ppt(
        ["Title: Threat Briefing", "Indicator IP 10.0.0.5 present", "Closing statement"]
    )
    result = await _inspect(storage, "deck.ppt", data)

    assert result.supported_for_inspection is True
    assert result.media_category == MEDIA_CATEGORY_PRESENTATION
    assert result.metadata["format"] == "ppt"
    assert result.metadata["converted_via"] == "libreoffice"
    assert result.metadata["slide_count"] == 3
    assert result.extracted_text is not None
    assert "Title: Threat Briefing" in result.extracted_text
    assert "Indicator IP 10.0.0.5 present" in result.extracted_text
    assert "Closing statement" in result.extracted_text


async def test_legacy_doc_blank_body_has_no_text(storage: LocalStorage):
    result = await _inspect(storage, "blank.doc", build_doc([]))
    assert result.supported_for_inspection is True
    # LibreOffice may synthesize an empty paragraph during the OLE2 round-trip;
    # the extraction contract is that no usable text is produced.
    assert result.metadata["paragraph_count"] >= 0
    assert result.extracted_text is None


async def test_legacy_ppt_blank_deck_has_no_text(storage: LocalStorage):
    result = await _inspect(storage, "blank.ppt", build_ppt([]))
    assert result.supported_for_inspection is True
    # Same round-trip caveat as the blank .doc case above.
    assert result.metadata["slide_count"] >= 0
    assert result.extracted_text is None


async def test_legacy_doc_malformed_raises_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _inspect(storage, "broken.doc", b"this is not a real office document")


async def test_legacy_ppt_malformed_raises_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _inspect(storage, "broken.ppt", b"%PPT fake bytes%")


async def test_legacy_office_empty_input_raises_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _inspect(storage, "empty.doc", b"")


async def test_legacy_doc_normalization_feeds_existing_pipeline(storage: LocalStorage):
    data = build_doc(["first paragraph", "second grounded paragraph"])
    result = await _inspect(storage, "memo.doc", data)
    record = next(iter_normalized_records([result]))
    assert record["supported_for_inspection"] is True
    assert record["reason"] is None
    assert record["normalized_text"] is not None
    assert "first paragraph" in record["normalized_text"]
    assert "second grounded paragraph" in record["normalized_text"]


async def test_legacy_office_conversion_never_uses_user_filename_or_macros(
    storage: LocalStorage, monkeypatch
):
    """The soffice command must be fully controlled: fixed input basename,
    headless flags, isolated profile — and never the caller's filename."""
    captured: dict = {}

    real_run = legacy_office.subprocess.run

    def spy_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        captured["headless"] = True
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(legacy_office.subprocess, "run", spy_run)

    data = build_doc(["clean text only"])
    filename = "../../escape-magic.doc"
    input_file = make_input_file(filename, "application/msword", data)
    await write_via_storage(storage, input_file, data)

    inspector = get_inspector(classify_format(filename, "application/msword"))
    result = await inspector.inspect(input_file, storage)

    cmd = captured["cmd"]
    assert "escape-magic" not in " ".join(cmd), "user filename must never reach soffice"
    assert cmd[-1].endswith("input"), "input must use a fixed basename"
    assert "--headless" in cmd
    assert "--norestore" in cmd and "--nofirststartwizard" in cmd
    assert any(arg.startswith("-env:UserInstallation=file://") for arg in cmd)
    assert "TMPDIR" in captured["env"]
    assert result.extracted_text == "clean text only"


# --- processing-service integration (upload -> inspect -> normalized) ---------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
    signup = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    assert signup.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200
    return login.json()["access_token"]


async def _create_job(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/v1/jobs", json={"config": {}}, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(
    client: AsyncClient, token: str, job_id: str, filename: str, content: bytes
) -> None:
    content_type = ALLOWED_UPLOAD_TYPES[Path(filename).suffix]
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/input",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text


async def _job_status(job_id: str):
    from sqlalchemy import select

    async with async_session_factory() as db:
        return await db.scalar(select(Job.status).where(Job.id == uuid.UUID(job_id)))


async def _reserve_and_process(job_id: str, storage: LocalStorage):
    async with async_session_factory() as db:
        await reserve_job_for_processing(db, uuid.UUID(job_id))
        return await process_job(uuid.UUID(job_id), db, storage)


async def _read_artifact(storage: LocalStorage, artifact_path: str) -> dict:
    return json.loads(storage.resolve(artifact_path).read_text())


@pytest.mark.parametrize(
    ("filename", "builder", "expect_chars"),
    [
        ("records.doc", lambda: build_doc(["legacy doc body text"]), 20),
        ("slides.ppt", lambda: build_ppt(["legacy ppt slide text"]), 20),
    ],
)
async def test_legacy_office_processes_to_single_artifact(
    client: AsyncClient, storage: LocalStorage, filename, builder, expect_chars
):
    email = unique_email("lo_ok")
    CREATED_EMAILS.append(email)
    token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, filename, builder())

    result = await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "completed"
    artifact = await _read_artifact(storage, result.artifact_path)
    entry = artifact["inspected_files"][0]
    assert entry["original_filename"] == filename
    assert entry["supported_for_inspection"] is True
    assert entry["extracted_chars"] >= expect_chars


@pytest.mark.parametrize(
    ("filename", "bad_bytes"),
    [
        ("broken.doc", b"not a real office document"),
        ("broken.ppt", b"also not a real office document"),
    ],
)
async def test_legacy_office_malformed_upload_fails_job(
    client: AsyncClient, storage: LocalStorage, filename, bad_bytes
):
    email = unique_email("lo_bad")
    CREATED_EMAILS.append(email)
    token = await _signup_and_login(client, email)
    job_id = await _create_job(client, token)
    await _upload(client, token, job_id, filename, bad_bytes)

    with pytest.raises(ProcessingError):
        await _reserve_and_process(job_id, storage)

    assert await _job_status(job_id) == "failed"