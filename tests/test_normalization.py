"""Stage 13 — normalization unit tests.

Coverage is independent of persistence: the deterministic text normalizer,
UTF-8-safe truncation, record building, input ordering, and the incremental
(in-memory) iterator that the future Stage 14 boundary will consume. An
in-memory integration test exercises the Stage 12 (inspection) -> Stage 13
(normalization) boundary for TXT/PDF/DOCX without writing normalized content
to any artifact, database row, or storage path.
"""

import io
import uuid
from collections.abc import AsyncIterator

import pytest

from app.core.formats import MEDIA_CATEGORY_DOCUMENT, classify_format
from app.models.input_file import InputFile
from app.processing.inspection import (
    DOCXInspector,
    InspectionResult,
    PDFInspector,
    TextInspector,
    get_inspector,
)
from app.processing.normalization import (
    _truncate_to_utf8_bytes,
    iter_normalized_records,
    normalize_text,
)
from app.storage.local import LocalStorage

try:
    from docx import Document as _DocxDocument
except ImportError:  # pragma: no cover
    _DocxDocument = None

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


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


def test_iter_preserves_input_order():
    a = _result("b.pdf", text="second")
    b = _result("a.pdf", text="first")
    records = list(iter_normalized_records([b, a]))
    assert [r["original_filename"] for r in records] == ["a.pdf", "b.pdf"]
    assert records[0]["normalized_text"] == "first\n"
    assert records[1]["normalized_text"] == "second\n"


def test_iter_consumes_incrementally_without_materializing():
    results = [_result(f"f{i}.txt", text=f"text {i}") for i in range(5)]
    pulled: list[int] = []

    def source():
        for index, result in enumerate(results):
            pulled.append(index)
            yield result

    iterator = iter_normalized_records(source())
    first = next(iterator)

    assert first["original_filename"] == "f0.txt"
    assert pulled == [0], "iterator must not pull the whole input upfront"
    assert hasattr(iterator, "__next__")


def test_record_fields_for_supported_file():
    record = list(iter_normalized_records([_result("paper.pdf", text="Hi\n")]))[0]
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
    record = list(iter_normalized_records([InspectionResult.unsupported(file, classification)]))[0]
    assert record["supported_for_inspection"] is False
    assert record["normalized_text"] is None
    assert record["normalized_char_count"] is None
    assert record["reason"] == "no inspector registered for media category"


def test_record_for_supported_but_empty_extraction():
    record = list(iter_normalized_records([_result("scan.pdf", text=None)]))[0]
    assert record["supported_for_inspection"] is True
    assert record["normalized_text"] is None
    assert record["reason"] == "no extractable text"


def test_record_flags_truncated_output():
    record = list(iter_normalized_records([_result("big.txt", text="y" * 100)], cap_bytes=10))[0]
    assert record["truncated"] is True
    assert len(record["normalized_text"].encode("utf-8")) <= 10


def test_record_within_cap_is_not_truncated():
    record = list(iter_normalized_records([_result("ok.txt", text="tiny")], cap_bytes=10))[0]
    assert record["truncated"] is False
    assert record["normalized_text"] == "tiny\n"


# --- in-memory Stage 12 -> Stage 13 boundary ----------------------------------


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
        storage_path=f"{uuid.uuid4()}/input/{filename}",
    )


async def test_in_memory_boundary_normalizes_txt_pdf_docx(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")

    txt_source = "  Alpha  \r\nBeta\t gamma\r\n\r\nLast.  "
    pdf_data = build_pdf(["PDF line"])
    docx_data = build_docx(["First line", "Second line"])
    payloads = [
        (txt_source.encode(), "text/plain", "notes.txt"),
        (pdf_data, "application/pdf", "report.pdf"),
        (docx_data, _DOCX_MIME, "memo.docx"),
    ]

    candidates = []
    for data, content_type, filename in payloads:
        input_file = make_input_file(filename, content_type, data)
        await storage.save(
            _bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1
        )
        candidates.append(input_file)

    inspections = []
    for input_file in candidates:
        classification = classify_format(
            input_file.original_filename, input_file.content_type
        )
        inspector = get_inspector(classification)
        assert inspector is not None
        inspections.append(await inspector.inspect(input_file, storage))

    records = list(iter_normalized_records(inspections))
    assert [r["original_filename"] for r in records] == ["notes.txt", "report.pdf", "memo.docx"]

    notes = records[0]
    assert notes["normalized_text"] == normalize_text(txt_source)
    assert notes["normalized_char_count"] == len(normalize_text(txt_source))
    assert notes["truncated"] is False
    assert notes["reason"] is None

    pdf = records[1]
    assert pdf["supported_for_inspection"] is True
    assert "PDF line" in pdf["normalized_text"]

    docx = records[2]
    assert docx["supported_for_inspection"] is True
    assert docx["normalized_text"] == "First line\nSecond line\n"


@pytest.mark.skipif(_DocxDocument is None, reason="python-docx not installed")
async def test_in_memory_boundary_includes_docx_inspector(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    data = build_docx(["First", "Second"])
    input_file = make_input_file("memo.docx", _DOCX_MIME, data)
    await storage.save(_bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1)

    result = await DOCXInspector().inspect(input_file, storage)
    records = list(iter_normalized_records([result]))

    assert records[0]["original_filename"] == "memo.docx"
    assert records[0]["normalized_text"] == "First\nSecond\n"


async def test_in_memory_boundary_includes_txt_and_pdf_inspectors(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    txt = make_input_file("notes.txt", "text/plain", b"hello\r\nworld\n")
    txt_data = b"hello\r\nworld\n"
    await storage.save(_bytes_chunks(txt_data), txt.storage_path, max_size=len(txt_data) + 1)
    pdf = make_input_file("report.pdf", "application/pdf", build_pdf(["Page one"]))
    pdf_data = build_pdf(["Page one"])
    await storage.save(_bytes_chunks(pdf_data), pdf.storage_path, max_size=len(pdf_data) + 1)

    txt_result = await TextInspector().inspect(txt, storage)
    pdf_result = await PDFInspector().inspect(pdf, storage)
    records = list(iter_normalized_records([txt_result, pdf_result]))

    assert records[0]["normalized_text"] == "hello\nworld\n"
    assert "Page one" in records[1]["normalized_text"]
    assert pdf_result.metadata["page_count"] == 1