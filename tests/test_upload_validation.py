import pytest

from app.core.uploads import (
    ACCEPTED_UPLOAD_CONTENT_TYPES,
    ALLOWED_UPLOAD_TYPES,
    UploadValidationError,
    normalize_filename,
    validate_upload_type,
)

# The canonical 46-format contract (product-approved), in publication order.
EXPECTED_ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".csv",
    ".tsv",
    ".txt",
    ".log",
    ".md",
    ".markdown",
    ".rtf",
    ".xml",
    ".rss",
    ".atom",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".tiff",
    ".tif",
    ".bmp",
    ".mp3",
    ".wav",
    ".m4a",
    ".ogg",
    ".flac",
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".stix",
    ".taxii",
    ".json",
    ".jsonl",
    ".evtx",
    ".syslog",
    ".yara",
    ".sigma",
    ".py",
    ".sh",
    ".ps1",
]


@pytest.mark.parametrize("ext", EXPECTED_ALLOWED_EXTENSIONS)
def test_allowed_extensions_accepted(ext):
    content_type, returned_ext = validate_upload_type(f"report{ext}", None)
    assert returned_ext == ext
    assert content_type == ALLOWED_UPLOAD_TYPES[ext]


def test_allowed_upload_types_are_exactly_the_forty_six_formats():
    assert set(ALLOWED_UPLOAD_TYPES) == set(EXPECTED_ALLOWED_EXTENSIONS)
    assert len(EXPECTED_ALLOWED_EXTENSIONS) == 46


def test_each_allowed_format_accepts_its_alternate_mime_types():
    for ext, accepted in ACCEPTED_UPLOAD_CONTENT_TYPES.items():
        for content_type in accepted:
            returned_type, returned_ext = validate_upload_type(f"sample{ext}", content_type)
            assert returned_ext == ext
            # The stored content type is always the canonical one.
            assert returned_type == ALLOWED_UPLOAD_TYPES[ext]


def test_extension_is_case_insensitive():
    content_type, extension = validate_upload_type("REPORT.PDF", "Application/PDF; charset=utf-8")
    assert extension == ".pdf"
    assert content_type == "application/pdf"


@pytest.mark.parametrize(
    "filename",
    [
        "notes.zip",
        "run.exe",
        "archive.tar.gz",
        "script.js",
        "page.html",
        "evil.bat",
        "plugin.dll",
        "photo.gif",
        "config.ini",
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
    ("filename", "mismatched"),
    [
        ("photo.png", "text/plain"),
        ("song.mp3", "application/pdf"),
        ("script.py", "application/pdf"),
        ("notes.md", "application/json"),
        ("rule.xml", "image/png"),
    ],
)
def test_known_content_type_must_match_new_formats(filename, mismatched):
    with pytest.raises(UploadValidationError):
        validate_upload_type(filename, mismatched)


def test_former_script_and_svg_types_are_now_allowed():
    _, ext = validate_upload_type("script.py", "text/x-python")
    assert ext == ".py"
    _, ext = validate_upload_type("script.py", "text/plain")
    assert ext == ".py"
    _, ext = validate_upload_type("icons.svg", "image/svg+xml")
    assert ext == ".svg"


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