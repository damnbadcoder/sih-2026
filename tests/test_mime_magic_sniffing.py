import pytest
from app.core.formats import verify_magic_match
from app.processing.inspection.magic import detect_magic


def test_valid_pdf_magic():
    header = b"%PDF-1.7\r\n" + b"\x00" * 500
    assert detect_magic(header) == "pdf"
    assert verify_magic_match("pdf", ".pdf") is True


def test_valid_evtx_magic():
    header = b"ElfFile\x00" + b"\x00" * 500
    assert detect_magic(header) == "evtx"
    assert verify_magic_match("evtx", ".evtx") is True


def test_spoofed_extension_detection():
    header = b"PK\x03\x04" + b"\x00" * 500
    assert detect_magic(header) == "zip_docx"
    assert verify_magic_match("zip_docx", ".pdf") is False
    