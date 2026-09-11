from pathlib import PurePosixPath

ALLOWED_UPLOAD_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

_KNOWN_TRANSPORT_TYPES = {"", "application/octet-stream"}


class UploadValidationError(ValueError):
    """Raised when an uploaded file is not an allowed document type."""


def normalize_filename(filename: str) -> str:
    """Strip any directory components from a client-supplied filename.

    Only the basename is kept (forward- and backslash separated) so the raw
    client value is never used for anything but display metadata.
    """
    cleaned = filename.replace("\\", "/")
    name = PurePosixPath(cleaned).name.strip()
    return name or "upload"


def validate_upload_type(filename: str, content_type: str | None) -> tuple[str, str]:
    """Validate a client upload against the allowed document types.

    The file extension is authoritative (the allowlist above); the MIME header
    is not trusted on its own. Returns ``(stored_content_type, extension)`` or
    raises :class:`UploadValidationError`.
    """
    name = normalize_filename(filename)
    ext = PurePosixPath(name).suffix.lower()
    canonical = ALLOWED_UPLOAD_TYPES.get(ext)
    if canonical is None:
        raise UploadValidationError(
            f"file type not supported (allowed: {', '.join(ALLOWED_UPLOAD_TYPES)})"
        )

    submitted = (content_type or "").split(";", 1)[0].strip().lower()
    if (
        submitted not in _KNOWN_TRANSPORT_TYPES
        and submitted in ALLOWED_UPLOAD_TYPES.values()
        and submitted != canonical
    ):
        raise UploadValidationError(
            f"content type {submitted!r} does not match file extension {ext!r}"
        )

    return canonical, ext