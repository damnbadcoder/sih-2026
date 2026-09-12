import csv
import io
import json
import logging
from pathlib import PurePosixPath
from typing import Any

from app.config import get_settings
from app.core.formats import MEDIA_CATEGORY_TEXT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError
from app.storage import Storage, StorageError

logger = logging.getLogger(__name__)

_READ_CHUNK_BYTES = 64 * 1024
_MAX_FLATTEN_DEPTH = 64

# Plain text/configuration content: decoded as-is. Scripts (.py/.sh/.ps1),
# rules (.yara) and logs are read as inert text only — never executed.
_PLAIN_TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".markdown", ".log", ".syslog", ".yara", ".py", ".sh", ".ps1"}
)
# Delimited text: rows are rendered as tab-separated, one line per row.
_DELIMITED_TEXT_EXTENSIONS = frozenset({".csv", ".tsv"})
# Structured text: JSON/JSONL are deterministically flattened into text lines.
_JSON_EXTENSIONS = frozenset({".json"})
_JSONL_EXTENSIONS = frozenset({".jsonl"})


class TextInspector(BaseInspector):
    """Plain, delimited and JSON text inspector.

    Covers plain text (``.txt``), Markdown (``.md``/``.markdown``), log-style
    text (``.log``/``.syslog``), configuration/rules content (``.yara``) and
    script sources (``.py``/``.sh``/``.ps1``) — all decoded as UTF-8 with a BOM
    tolerance and lossy fallback. Scripts and rules are treated strictly as
    inert text; nothing is imported or executed.

    ``.csv``/``.tsv`` rows are rendered as tab-separated lines of their
    non-empty cells, and ``.json``/``.jsonl`` documents are flattened into
    deterministic ``key: value`` lines so downstream normalization and
    grounding receive line-structured text.
    """

    media_category = MEDIA_CATEGORY_TEXT
    supported_extensions = frozenset(
        _PLAIN_TEXT_EXTENSIONS
        | _DELIMITED_TEXT_EXTENSIONS
        | _JSON_EXTENSIONS
        | _JSONL_EXTENSIONS
    )
    supported_mime_types = frozenset(
        {
            "text/plain",
            "text/markdown",
            "text/x-markdown",
            "text/csv",
            "text/tab-separated-values",
            "application/json",
            "application/x-ndjson",
            "application/ndjson",
            "text/x-python",
            "text/x-sh",
            "application/x-sh",
            "application/powershell",
        }
    )

    def __init__(self, max_text_bytes: int | None = None) -> None:
        self._max_text_bytes = max_text_bytes

    def _max_bytes(self) -> int:
        if self._max_text_bytes is not None:
            return self._max_text_bytes
        return get_settings().MAX_UPLOAD_SIZE_BYTES

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        data, truncated = await _read_bounded(file, storage, self._max_bytes())
        extension = PurePosixPath(file.original_filename).suffix.lower()
        if extension in _DELIMITED_TEXT_EXTENSIONS:
            return _extract_delimited(data, extension, truncated)
        if extension in _JSON_EXTENSIONS:
            return _extract_json(data, truncated)
        if extension in _JSONL_EXTENSIONS:
            return _extract_jsonl(data, truncated)
        text = _decode_text(data)
        return text, {"truncated": truncated, "char_count": len(text)}


def _extract_delimited(
    data: bytes, extension: str, truncated: bool
) -> tuple[str | None, dict[str, Any]]:
    text = _decode_text(data)
    delimiter = "\t" if extension == ".tsv" else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    lines: list[str] = []
    row_count = 0
    char_count = 0
    for row in reader:
        row_count += 1
        values = [cell.strip() for cell in row if cell.strip()]
        if values:
            line = "\t".join(values)
            lines.append(line)
            char_count += len(line)
    rendered = "\n".join(lines)
    return (rendered or None), {
        "format": "tsv" if extension == ".tsv" else "csv",
        "row_count": row_count,
        "char_count": char_count,
        "truncated": truncated,
    }


def _extract_json(data: bytes, truncated: bool) -> tuple[str | None, dict[str, Any]]:
    text = _decode_text(data)
    if not text.strip():
        return None, {"format": "json", "char_count": 0, "truncated": truncated}
    try:
        value = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise InspectionError("JSON file is malformed or unreadable") from exc
    rendered = "\n".join(flatten_json(value))
    return (rendered or None), {
        "format": "json",
        "char_count": len(rendered),
        "truncated": truncated,
    }


def _extract_jsonl(data: bytes, truncated: bool) -> tuple[str | None, dict[str, Any]]:
    text = _decode_text(data)
    lines: list[str] = []
    line_count = 0
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        line_count += 1
        try:
            value = json.loads(stripped)
        except (ValueError, RecursionError) as exc:
            raise InspectionError("JSONL file is malformed or unreadable") from exc
        lines.extend(flatten_json(value))
    rendered = "\n".join(lines)
    return (rendered or None), {
        "format": "jsonl",
        "line_count": line_count,
        "char_count": len(rendered),
        "truncated": truncated,
    }


def json_scalar(value: Any) -> str:
    """Render a JSON/YAML scalar as a single deterministic line fragment."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return (
            value.replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
    return str(value)


def flatten_json(value: Any, *, prefix: str = "", _depth: int = 0) -> list[str]:
    """Flatten nested JSON/YAML data into deterministic ``key: value`` lines."""
    if _depth > _MAX_FLATTEN_DEPTH:
        return [f"{prefix}: <max-depth>"] if prefix else ["<max-depth>"]
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten_child(item, child, out, _depth)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten_child(item, f"{prefix}[{index}]", out, _depth)
    else:
        out.append(json_scalar(value))
    return out


def _flatten_child(item: Any, child: str, out: list[str], depth: int) -> None:
    if isinstance(item, (dict, list)):
        if not item:
            out.append(f"{child}: {json.dumps(item)}")
        else:
            out.extend(flatten_json(item, prefix=child, _depth=depth + 1))
    else:
        out.append(f"{child}: {json_scalar(item)}")


async def _read_bounded(
    file: InputFile, storage: Storage, limit: int
) -> tuple[bytes, bool]:
    """Stream up to ``limit`` bytes from ``storage``; report if cut off."""
    data = bytearray()
    truncated = False
    try:
        async for chunk in storage.read_chunks(
            file.storage_path, chunk_size=_READ_CHUNK_BYTES
        ):
            remaining = limit - len(data)
            if len(chunk) > remaining:
                if remaining > 0:
                    data.extend(chunk[:remaining])
                truncated = True
                break
            data.extend(chunk)
    except StorageError as exc:
        raise InspectionError(
            f"stored input file could not be read: {file.storage_path}"
        ) from exc
    if not truncated and len(data) != file.file_size:
        raise InspectionError(f"stored input file size mismatch: {file.storage_path}")
    return bytes(data), truncated


def _decode_text(data: bytes) -> str:
    """Decode as UTF-8, tolerating a BOM and invalid byte sequences.

    Un-decodable bytes are replaced so a malformed file never crashes the
    worker; the caller can still inspect the recovered text.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")