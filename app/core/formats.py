from dataclasses import dataclass
from pathlib import PurePosixPath

MEDIA_CATEGORY_TEXT = "text"
MEDIA_CATEGORY_DOCUMENT = "document"
MEDIA_CATEGORY_PRESENTATION = "presentation"
MEDIA_CATEGORY_IMAGE = "image"
MEDIA_CATEGORY_AUDIO = "audio"
MEDIA_CATEGORY_VIDEO = "video"
MEDIA_CATEGORY_UNKNOWN = "unknown"

MEDIA_CATEGORIES: frozenset[str] = frozenset(
    {
        MEDIA_CATEGORY_TEXT,
        MEDIA_CATEGORY_DOCUMENT,
        MEDIA_CATEGORY_PRESENTATION,
        MEDIA_CATEGORY_IMAGE,
        MEDIA_CATEGORY_AUDIO,
        MEDIA_CATEGORY_VIDEO,
        MEDIA_CATEGORY_UNKNOWN,
    }
)

EXTENSION_CATEGORIES: dict[str, str] = {
    ".txt": MEDIA_CATEGORY_TEXT,
    ".md": MEDIA_CATEGORY_TEXT,
    ".markdown": MEDIA_CATEGORY_TEXT,
    ".csv": MEDIA_CATEGORY_TEXT,
    ".tsv": MEDIA_CATEGORY_TEXT,
    ".json": MEDIA_CATEGORY_TEXT,
    ".xml": MEDIA_CATEGORY_TEXT,
    ".yaml": MEDIA_CATEGORY_TEXT,
    ".yml": MEDIA_CATEGORY_TEXT,
    ".log": MEDIA_CATEGORY_TEXT,
    ".html": MEDIA_CATEGORY_TEXT,
    ".htm": MEDIA_CATEGORY_TEXT,
    ".rst": MEDIA_CATEGORY_TEXT,
    ".tex": MEDIA_CATEGORY_TEXT,
    ".ini": MEDIA_CATEGORY_TEXT,
    ".cfg": MEDIA_CATEGORY_TEXT,
    ".conf": MEDIA_CATEGORY_TEXT,
    ".pdf": MEDIA_CATEGORY_DOCUMENT,
    ".doc": MEDIA_CATEGORY_DOCUMENT,
    ".docx": MEDIA_CATEGORY_DOCUMENT,
    ".odt": MEDIA_CATEGORY_DOCUMENT,
    ".rtf": MEDIA_CATEGORY_DOCUMENT,
    ".xls": MEDIA_CATEGORY_DOCUMENT,
    ".xlsx": MEDIA_CATEGORY_DOCUMENT,
    ".xlsm": MEDIA_CATEGORY_DOCUMENT,
    ".ods": MEDIA_CATEGORY_DOCUMENT,
    ".pages": MEDIA_CATEGORY_DOCUMENT,
    ".ppt": MEDIA_CATEGORY_PRESENTATION,
    ".pptx": MEDIA_CATEGORY_PRESENTATION,
    ".odp": MEDIA_CATEGORY_PRESENTATION,
    ".key": MEDIA_CATEGORY_PRESENTATION,
    ".png": MEDIA_CATEGORY_IMAGE,
    ".jpg": MEDIA_CATEGORY_IMAGE,
    ".jpeg": MEDIA_CATEGORY_IMAGE,
    ".gif": MEDIA_CATEGORY_IMAGE,
    ".webp": MEDIA_CATEGORY_IMAGE,
    ".bmp": MEDIA_CATEGORY_IMAGE,
    ".tif": MEDIA_CATEGORY_IMAGE,
    ".tiff": MEDIA_CATEGORY_IMAGE,
    ".svg": MEDIA_CATEGORY_IMAGE,
    ".heic": MEDIA_CATEGORY_IMAGE,
    ".heif": MEDIA_CATEGORY_IMAGE,
    ".avif": MEDIA_CATEGORY_IMAGE,
    ".ico": MEDIA_CATEGORY_IMAGE,
    ".mp3": MEDIA_CATEGORY_AUDIO,
    ".wav": MEDIA_CATEGORY_AUDIO,
    ".flac": MEDIA_CATEGORY_AUDIO,
    ".aac": MEDIA_CATEGORY_AUDIO,
    ".ogg": MEDIA_CATEGORY_AUDIO,
    ".oga": MEDIA_CATEGORY_AUDIO,
    ".opus": MEDIA_CATEGORY_AUDIO,
    ".m4a": MEDIA_CATEGORY_AUDIO,
    ".wma": MEDIA_CATEGORY_AUDIO,
    ".weba": MEDIA_CATEGORY_AUDIO,
    ".mid": MEDIA_CATEGORY_AUDIO,
    ".midi": MEDIA_CATEGORY_AUDIO,
    ".mp4": MEDIA_CATEGORY_VIDEO,
    ".mkv": MEDIA_CATEGORY_VIDEO,
    ".mov": MEDIA_CATEGORY_VIDEO,
    ".avi": MEDIA_CATEGORY_VIDEO,
    ".webm": MEDIA_CATEGORY_VIDEO,
    ".wmv": MEDIA_CATEGORY_VIDEO,
    ".flv": MEDIA_CATEGORY_VIDEO,
    ".m4v": MEDIA_CATEGORY_VIDEO,
    ".mpeg": MEDIA_CATEGORY_VIDEO,
    ".mpg": MEDIA_CATEGORY_VIDEO,
    ".3gp": MEDIA_CATEGORY_VIDEO,
    ".ts": MEDIA_CATEGORY_VIDEO,
}

MIME_CATEGORIES: dict[str, str] = {
    "text/plain": MEDIA_CATEGORY_TEXT,
    "text/markdown": MEDIA_CATEGORY_TEXT,
    "text/csv": MEDIA_CATEGORY_TEXT,
    "text/html": MEDIA_CATEGORY_TEXT,
    "text/xml": MEDIA_CATEGORY_TEXT,
    "application/json": MEDIA_CATEGORY_TEXT,
    "application/xml": MEDIA_CATEGORY_TEXT,
    "application/pdf": MEDIA_CATEGORY_DOCUMENT,
    "application/msword": MEDIA_CATEGORY_DOCUMENT,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        MEDIA_CATEGORY_DOCUMENT
    ),
    "application/vnd.oasis.opendocument.text": MEDIA_CATEGORY_DOCUMENT,
    "application/rtf": MEDIA_CATEGORY_DOCUMENT,
    "application/vnd.ms-excel": MEDIA_CATEGORY_DOCUMENT,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": MEDIA_CATEGORY_DOCUMENT,
    "application/vnd.oasis.opendocument.spreadsheet": MEDIA_CATEGORY_DOCUMENT,
    "application/vnd.ms-powerpoint": MEDIA_CATEGORY_PRESENTATION,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        MEDIA_CATEGORY_PRESENTATION
    ),
    "application/vnd.oasis.opendocument.presentation": MEDIA_CATEGORY_PRESENTATION,
    "image/png": MEDIA_CATEGORY_IMAGE,
    "image/jpeg": MEDIA_CATEGORY_IMAGE,
    "image/gif": MEDIA_CATEGORY_IMAGE,
    "image/webp": MEDIA_CATEGORY_IMAGE,
    "image/bmp": MEDIA_CATEGORY_IMAGE,
    "image/tiff": MEDIA_CATEGORY_IMAGE,
    "image/svg+xml": MEDIA_CATEGORY_IMAGE,
    "image/heic": MEDIA_CATEGORY_IMAGE,
    "image/heif": MEDIA_CATEGORY_IMAGE,
    "image/avif": MEDIA_CATEGORY_IMAGE,
    "image/vnd.microsoft.icon": MEDIA_CATEGORY_IMAGE,
    "audio/mpeg": MEDIA_CATEGORY_AUDIO,
    "audio/wav": MEDIA_CATEGORY_AUDIO,
    "audio/x-wav": MEDIA_CATEGORY_AUDIO,
    "audio/flac": MEDIA_CATEGORY_AUDIO,
    "audio/aac": MEDIA_CATEGORY_AUDIO,
    "audio/ogg": MEDIA_CATEGORY_AUDIO,
    "audio/opus": MEDIA_CATEGORY_AUDIO,
    "audio/mp4": MEDIA_CATEGORY_AUDIO,
    "audio/x-m4a": MEDIA_CATEGORY_AUDIO,
    "audio/x-ms-wma": MEDIA_CATEGORY_AUDIO,
    "audio/webm": MEDIA_CATEGORY_AUDIO,
    "video/mp4": MEDIA_CATEGORY_VIDEO,
    "video/quicktime": MEDIA_CATEGORY_VIDEO,
    "video/x-msvideo": MEDIA_CATEGORY_VIDEO,
    "video/webm": MEDIA_CATEGORY_VIDEO,
    "video/x-ms-wmv": MEDIA_CATEGORY_VIDEO,
    "video/mpeg": MEDIA_CATEGORY_VIDEO,
    "video/x-flv": MEDIA_CATEGORY_VIDEO,
    "video/3gpp": MEDIA_CATEGORY_VIDEO,
}


@dataclass(frozen=True)
class FormatClass:
    """Result of classifying a user-supplied file without trusting it."""

    media_category: str
    extension: str | None
    mime_type: str | None


def classify_format(filename: str, content_type: str | None) -> FormatClass:
    """Classify a file into a broad media category using extension and MIME.

    Neither the extension nor the client-provided content type is trusted on
    its own. A recognized extension is preferred; the MIME type is only a
    fallback and ``application/octet-stream`` carries no signal. When the two
    sources contradict each other the file is classified as ``unknown`` so a
    later content-signature stage can resolve the ambiguity.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name
    ext = PurePosixPath(name).suffix.lower() or None
    mime = (content_type or "").split(";", 1)[0].strip().lower() or None

    extension_category = EXTENSION_CATEGORIES.get(ext) if ext else None
    mime_category = MIME_CATEGORIES.get(mime) if mime else None

    if extension_category is not None and mime_category is not None:
        category = (
            extension_category
            if extension_category == mime_category
            else MEDIA_CATEGORY_UNKNOWN
        )
    else:
        category = extension_category or mime_category or MEDIA_CATEGORY_UNKNOWN

    return FormatClass(media_category=category, extension=ext, mime_type=mime)

def verify_magic_match(detected_magic: str | None, declared_ext: str) -> bool:
    if detected_magic is None:
        return True

    ext_map = {
        "pdf": ["pdf"],
        "zip_docx": ["docx", "xlsx", "pptx", "zip"],
        "ole": ["doc", "xls", "ppt"],
        "png": ["png"],
        "jpeg": ["jpg", "jpeg"],
        "gif": ["gif"],
        "rtf": ["rtf"],
        "evtx": ["evtx"],
        "mp4": ["mp4"],
        "wav": ["wav"],
    }

    clean_ext = declared_ext.lstrip(".").lower()
    allowed_extensions = ext_map.get(detected_magic, [])

    return clean_ext in allowed_extensions