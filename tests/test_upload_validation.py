import pytest

from app.core.uploads import (
    ALLOWED_UPLOAD_TYPES,
    UploadValidationError,
    normalize_filename,
    validate_upload_type,
)


@pytest.mark.parametrize(
    "ext",
    [".mp3", ".mp4", ".docx", ".xlsx", ".pdf", ".png", ".jpeg", ".jpg", ".txt", ".md"],
)
def test_allowed_extensions_accepted(ext):
    content_type, returned_ext = validate_upload_type(f"report{ext}", None)
    assert returned_ext == ext
    assert content_type == ALLOWED_UPLOAD_TYPES[ext]


def test_allowed_upload_types_are_exactly_the_ten_required_formats():
    assert set(ALLOWED_UPLOAD_TYPES) == {
        ".mp3",
        ".mp4",
        ".docx",
        ".xlsx",
        ".pdf",
        ".png",
        ".jpeg",
        ".jpg",
        ".txt",
        ".md",
    }


def test_extension_is_case_insensitive():
    content_type, extension = validate_upload_type("REPORT.PDF", "Application/PDF; charset=utf-8")
    assert extension == ".pdf"
    assert content_type == "application/pdf"


@pytest.mark.parametrize(
    "filename",
    [
        "notes.zip",
        "run.exe",
        "evil.sh",
        "script.py",
        "ps1.ps1",
        "icons.svg",
        "slides.pptx",
        "archive.tar.gz",
        "noext",
    ],
)
def test_disallowed_extensions_rejected(filename):
    with pytest.raises(UploadValidationError):
        validate_upload_type(filename, "application/octet-stream")


def test_known_content_type_must_match_extension():
    with pytest.raises(UploadValidationError):
        validate_upload_type("report.pdf", "text/plain")


@pytest.mark.parametrize(
    ("filename", "mismatched"), [("photo.png", "text/plain"), ("song.mp3", "application/pdf")]
)
def test_known_content_type_must_match_new_formats(filename, mismatched):
    with pytest.raises(UploadValidationError):
        validate_upload_type(filename, mismatched)


def test_generic_content_type_falls_back_to_canonical():
    content_type, _ = validate_upload_type("report.pdf", "application/octet-stream")
    assert content_type == "application/pdf"


def test_empty_content_type_falls_back_to_canonical():
    content_type, _ = validate_upload_type("notes.txt", "")
    assert content_type == "text/plain"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../../etc/passwd", "passwd"),
        ("a/b/c/notes.txt", "notes.txt"),
        ("C:\\Docs\\in.pptx", "in.pptx"),
        ("  spaced name .txt", "spaced name .txt"),
        ("123", "123"),
    ],
)
def test_normalize_filename_strips_directory_components(raw, expected):
    assert normalize_filename(raw) == expected


def test_validation_uses_normalized_basename():
    content_type, extension = validate_upload_type("../../safe.pdf", "application/pdf")
    assert extension == ".pdf"
    assert content_type == "application/pdf"
    assert normalize_filename("../../safe.pdf") == "safe.pdf"