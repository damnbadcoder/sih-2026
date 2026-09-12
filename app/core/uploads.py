from pathlib import PurePosixPath

_CONTROL_CHARS = frozenset(chr(code) for code in (*range(0x00, 0x20), 0x7F))
_CONTROL_CHAR_TABLE = {ord(ch): None for ch in _CONTROL_CHARS}

# The product-approved input formats: EXACTLY these 46 (the canonical
# 46-format contract). Do not add or remove extensions here without an
# explicit product decision and a matching inspector + processing path.
#
# The allowlist is an extension-authoritative contract. Each entry maps the
# extension to its canonical (stored) media type plus the set of content
# types a client may legitimately send for that extension. The canonical
# value is always part of the accepted set.
#
# Registry coupling: a format never reaches processing as "unsupported" only
# once a registered inspector resolves it. New formats are added here (the
# upload contract) and to their inspector concurrently.
#
# Deliberately NOT copied from origin/samyak (02177bc): that commit's MIME
# map contains non-IANA types (application/powershell, application/jsonl)
# and naive single-value mappings that conflict with this architecture.
_ALLOWED_UPLOAD_FORMATS: dict[str, tuple[str, frozenset[str]]] = {
    # Documents / Text
    ".pdf": ("application/pdf", frozenset()),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset(),
    ),
    ".doc": ("application/msword", frozenset()),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        frozenset(),
    ),
    ".ppt": ("application/vnd.ms-powerpoint", frozenset()),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        frozenset(),
    ),
    ".xls": ("application/vnd.ms-excel", frozenset()),
    ".csv": ("text/csv", frozenset({"text/plain"})),
    ".tsv": ("text/tab-separated-values", frozenset({"text/plain"})),
    ".txt": ("text/plain", frozenset()),
    ".log": ("text/plain", frozenset()),
    ".md": ("text/markdown", frozenset({"text/plain"})),
    ".markdown": ("text/markdown", frozenset({"text/plain"})),
    ".rtf": ("application/rtf", frozenset({"text/rtf"})),
    # Web / Syndication
    ".xml": ("application/xml", frozenset({"text/xml"})),
    ".rss": ("application/rss+xml", frozenset({"application/xml", "text/xml"})),
    ".atom": ("application/atom+xml", frozenset({"application/xml", "text/xml"})),
    # Images
    ".png": ("image/png", frozenset()),
    ".jpg": ("image/jpeg", frozenset()),
    ".jpeg": ("image/jpeg", frozenset()),
    ".webp": ("image/webp", frozenset()),
    ".svg": ("image/svg+xml", frozenset()),
    ".tiff": ("image/tiff", frozenset()),
    ".tif": ("image/tiff", frozenset()),
    ".bmp": ("image/bmp", frozenset({"image/x-ms-bmp"})),
    # Audio / Video
    ".mp3": ("audio/mpeg", frozenset()),
    ".wav": ("audio/wav", frozenset({"audio/x-wav", "audio/wave"})),
    ".m4a": ("audio/mp4", frozenset({"audio/x-m4a", "audio/x-m4b"})),
    ".ogg": ("audio/ogg", frozenset({"application/ogg", "audio/vorbis"})),
    ".flac": ("audio/flac", frozenset({"audio/x-flac"})),
    ".mp4": ("video/mp4", frozenset()),
    ".mkv": ("video/x-matroska", frozenset()),
    ".mov": ("video/quicktime", frozenset()),
    ".avi": ("video/x-msvideo", frozenset({"video/avi"})),
    ".webm": ("video/webm", frozenset()),
    # Cybersecurity / Structured
    ".stix": ("application/json", frozenset({"application/xml", "text/xml"})),
    ".taxii": ("application/json", frozenset({"application/xml", "text/xml"})),
    ".json": ("application/json", frozenset()),
    ".jsonl": (
        "application/json",
        frozenset({"application/x-ndjson", "application/ndjson"}),
    ),
    ".evtx": ("application/octet-stream", frozenset()),
    ".syslog": ("text/plain", frozenset()),
    ".yara": ("text/plain", frozenset()),
    ".sigma": ("text/yaml", frozenset({"application/yaml"})),
    ".py": ("text/x-python", frozenset({"text/plain"})),
    ".sh": ("text/x-sh", frozenset({"application/x-sh", "text/x-shellscript"})),
    ".ps1": ("text/plain", frozenset({"application/powershell"})),
}

# Canonical media type per extension — the contract the upload API stores.
ALLOWED_UPLOAD_TYPES: dict[str, str] = {
    ext: canonical for ext, (canonical, _accepted) in _ALLOWED_UPLOAD_FORMATS.items()
}

# Per-extension sets of content types a client may legitimately submit. The
# extension remains authoritative; the submitted MIME header is only checked
# against this set so a truthful header is never rejected and a misleading
# header is.
ACCEPTED_UPLOAD_CONTENT_TYPES: dict[str, frozenset[str]] = {
    ext: frozenset({canonical, *accepted})
    for ext, (canonical, accepted) in _ALLOWED_UPLOAD_FORMATS.items()
}

# Content types that are meaningful signals for at least one approved format.
# A submitted header that is known but not accepted for the file's extension
# indicates a mismatched upload and is rejected.
KNOWN_UPLOAD_CONTENT_TYPES: frozenset[str] = frozenset().union(
    *ACCEPTED_UPLOAD_CONTENT_TYPES.values()
)

# Transport-level markers that carry no format signal and must never trigger
# a mismatch rejection (they fall back to the canonical type).
_KNOWN_TRANSPORT_TYPES = {"", "application/octet-stream"}


class UploadValidationError(ValueError):
    """Raised when an uploaded file is not an allowed document type."""


def normalize_filename(filename: str) -> str:
    """Strip any directory components from a client-supplied filename.

    Only the basename is kept (forward- and backslash separated) so the raw
    client value is never used for anything but display metadata. ASCII
    control characters (including NUL, CR/LF and DEL) are removed so the
    stored display value cannot smuggle log/CSV-injection payloads.
    """
    cleaned = filename.replace("\\", "/").translate(_CONTROL_CHAR_TABLE)
    name = PurePosixPath(cleaned).name.strip()
    return name or "upload"


def validate_upload_type(filename: str, content_type: str | None) -> tuple[str, str]:
    """Validate a client upload against the approved 46-format contract.

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

    accepted = ACCEPTED_UPLOAD_CONTENT_TYPES.get(ext, frozenset({canonical}))
    submitted = (content_type or "").split(";", 1)[0].strip().lower()
    if (
        submitted not in _KNOWN_TRANSPORT_TYPES
        and submitted in KNOWN_UPLOAD_CONTENT_TYPES
        and submitted not in accepted
    ):
        raise UploadValidationError(
            f"content type {submitted!r} does not match file extension {ext!r}"
        )

    return canonical, ext