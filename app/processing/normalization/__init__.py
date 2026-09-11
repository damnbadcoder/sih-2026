"""Stage 13 — content normalization.

Turns the in-memory content produced by the Stage 12 inspection layer into a
clean, deterministic, normalized internal representation that later stages
(such as the Stage 14 transformation boundary) can consume.

Design rules:
- Pure, deterministic functions; identical input always yields identical output.
- Only meaning-preserving transformations: Unicode NFC composition, unified
  ``\\n`` line endings, removal of non-text control characters, and trailing
  per-line whitespace. Document structure (paragraph/page splitting already
  produced by inspectors, indentation, blank lines) is preserved as-is.
- The normalized representation is written to its own artifact and is only
  ever touched through the storage abstraction (never filesystem paths).
- Per-file byte caps keep serialized output bounded; truncated text is flagged
  explicitly so downstream consumers can decide what to do with it.
"""

import json
import re
import unicodedata
from collections.abc import AsyncIterator
from typing import Any

from app.config import get_settings
from app.processing.inspection import InspectionResult

NORMALIZED_ARTIFACT_TYPE = "normalized_content"

_NEWLINE_RE = re.compile(r"\r\n|\r|\n")
_TRAILING_LINE_WS_RE = re.compile(r"[ \t]+(?=\n|$)")
_C0_EXCEPT_TAB_NEWLINE = frozenset(
    chr(c) for c in range(32) if chr(c) not in "\t\n"
) | frozenset("\x7f")


def normalize_text(text: str) -> str:
    """Deterministically normalize extracted document text.

    Applies only meaning-preserving transformations:

    - Unicode NFC composition (never NFKC, which would alter semantics).
    - Unified ``\\n`` line endings (CRLF, CR, LF).
    - Removal of C0 control characters other than tab/newline.
    - Trailing horizontal whitespace removed from each line.
    - A single trailing newline at end of output.

    Blank lines (paragraph separators) and indentation are preserved.
    """
    if not text:
        return ""
    composed = unicodedata.normalize("NFC", text)
    unified = _NEWLINE_RE.sub("\n", composed)
    stripped = "".join(_ for _ in unified if _ not in _C0_EXCEPT_TAB_NEWLINE)
    lines = stripped.split("\n")
    cleaned = [_TRAILING_LINE_WS_RE.sub("", line) for line in lines]
    body = "\n".join(cleaned)
    if not body.strip("\n"):
        return ""
    return body.rstrip("\n") + "\n"


def _truncate_to_utf8_bytes(text: str, limit: int) -> tuple[str, bool]:
    """Truncate ``text`` to the longest UTF-8 prefix fitting in ``limit`` bytes.

    The prefix always ends on a character boundary, and the operation is
    deterministic. Returns ``(prefix, truncated)``.
    """
    if not text or limit <= 0:
        return ("", text != "") if limit <= 0 else (text, False)
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    cut = limit
    while True:
        try:
            prefix = data[:cut].decode("utf-8")
            break
        except UnicodeDecodeError:
            cut -= 1
    return prefix, True


def _record_for(result: InspectionResult, cap_bytes: int) -> dict[str, Any]:
    if not result.supported_for_inspection:
        return {
            "input_file_id": str(result.input_file_id),
            "original_filename": result.original_filename,
            "media_category": result.media_category,
            "extension": result.extension,
            "supported_for_inspection": False,
            "normalized_text": None,
            "normalized_char_count": None,
            "truncated": False,
            "reason": result.metadata.get("reason"),
        }

    raw = result.extracted_text
    if raw is None:
        return {
            "input_file_id": str(result.input_file_id),
            "original_filename": result.original_filename,
            "media_category": result.media_category,
            "extension": result.extension,
            "supported_for_inspection": True,
            "normalized_text": None,
            "normalized_char_count": None,
            "truncated": False,
            "reason": "no extractable text",
        }

    normalized = normalize_text(raw)
    truncated = False
    if normalized and len(normalized.encode("utf-8")) > cap_bytes:
        normalized, truncated = _truncate_to_utf8_bytes(normalized, cap_bytes)
    return {
        "input_file_id": str(result.input_file_id),
        "original_filename": result.original_filename,
        "media_category": result.media_category,
        "extension": result.extension,
        "supported_for_inspection": True,
        "normalized_text": normalized,
        "normalized_char_count": len(normalized),
        "truncated": truncated,
        "reason": None,
    }


def build_normalized_records(
    inspections: list[InspectionResult],
    *,
    cap_bytes: int | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic per-file normalized records.

    Record order matches the input-file order (the order inspections were
    produced in). ``cap_bytes`` bounds each file's normalized text to a UTF-8
    byte budget; it defaults to the configured upload-size limit so normalized
    output never exceeds what was permitted at upload time.
    """
    if cap_bytes is None:
        cap_bytes = get_settings().MAX_UPLOAD_SIZE_BYTES
    return [_record_for(result, cap_bytes) for result in inspections]


async def serialize_normalized_records(
    records: list[dict[str, Any]],
) -> AsyncIterator[bytes]:
    """Serialize normalized records as newline-delimited JSON (streaming).

    Each record becomes exactly one line of compact JSON with sorted keys, so
    serialization is byte-for-byte deterministic and can be streamed to
    storage without buffering the whole artifact in memory.
    """
    for record in records:
        line = json.dumps(
            record, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        yield line + b"\n"


def normalized_artifact_max_bytes(record_count: int) -> int:
    """Guard size for a normalized artifact.

    Worst case: record overhead plus JSON escaping roughly doubling per-file
    capped text. This is a streaming safety net, not a content policy.
    """
    cap = get_settings().MAX_UPLOAD_SIZE_BYTES
    return 2 * cap * max(record_count, 1) + 1024 * 1024