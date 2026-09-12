import contextlib
import logging
from typing import Any

from app.core.formats import MEDIA_CATEGORY_DOCUMENT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.storage import Storage

logger = logging.getLogger(__name__)

# Control-word destinations whose contents are metadata/font/UI boilerplate
# rather than document body text; groups opened with these words are skipped.
_DESTINATION_WORDS = frozenset(
    {
        "fonttbl",
        "colortbl",
        "stylesheet",
        "info",
        "generator",
        "themedata",
        "colorschememapping",
        "listtable",
        "listoverridetable",
        "latentstyles",
        "revtbl",
        "rsidtbl",
        "object",
        "pict",
        "nonshppict",
        "datafield",
        "fldinst",
        "header",
        "headerf",
        "headerl",
        "headerr",
        "footer",
        "footerf",
        "footerl",
        "footerr",
    }
)
_PARAGRAPH_WORDS = frozenset({"par", "line", "sect", "page"})

_RTF_MAGIC = b"{\\rtf"


class RTFInspector(BaseInspector):
    """RTF inspector: deterministic control-word stripping into plain text.

    ``.rtf`` is treated strictly as inert data. Only the file's magic prefix
    (:code:`{\\rtf`) is trusted; every control word is parsed conservatively —
    destination groups (fonts, tables, styles, headers/footers, embedded
    objects) are skipped, escaped characters and ``\\u`` unicode are decoded,
    and ``\\par``/``\\line`` become newlines. Nothing inside the file is
    executed, evaluated or rendered.
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".rtf"})
    supported_mime_types = frozenset({"application/rtf", "text/rtf"})

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        buffer = await stream_to_buffer(file, storage)
        try:
            header = buffer.read(64)
            if not header.lstrip().startswith(_RTF_MAGIC):
                raise InspectionError("RTF file is malformed or unreadable")
            buffer.seek(0)
            return _parse_rtf(buffer.read())
        finally:
            buffer.close()


def _parse_rtf(data: bytes) -> tuple[str | None, dict[str, Any]]:
    text = _rtf_to_text(data)
    stripped = text.strip()
    return (stripped or None), {"format": "rtf", "char_count": len(stripped)}


def _rtf_to_text(data: bytes) -> str:
    """Strip RTF control words/escape sequences into plain text.

    Pure, deterministic, standard-library only. Never expands document-supplied
    entities or groups, and never resolves anything external.
    """
    text = data.decode("latin-1", errors="replace")
    out: list[str] = []
    n = len(text)
    i = 0
    skip_stack: list[bool] = []
    fresh_stack: list[bool] = []
    pending_skip = 0
    uc_count = 1
    while i < n:
        ch = text[i]
        if pending_skip > 0:
            if ch == "\\":
                _word, _param, end = _parse_control(text, i)
                i = end
            else:
                i += 1
            pending_skip -= 1
            continue
        if ch == "{":
            skip_stack.append(False)
            fresh_stack.append(True)
            i += 1
            continue
        if ch == "}":
            if skip_stack:
                skip_stack.pop()
            if fresh_stack:
                fresh_stack.pop()
            if fresh_stack:
                fresh_stack[-1] = False
            i += 1
            continue
        if ch != "\\":
            if not any(skip_stack):
                if not ch.isspace() and fresh_stack:
                    fresh_stack[-1] = False
                out.append(ch)
            i += 1
            continue

        word, param, end = _parse_control(text, i)
        i = end
        in_skip = any(skip_stack)
        if word in ("\\", "{", "}"):
            if not in_skip:
                if fresh_stack:
                    fresh_stack[-1] = False
                out.append(word)
            continue
        if word == "'":
            if not in_skip and len(param) == 2:
                try:
                    if fresh_stack:
                        fresh_stack[-1] = False
                    out.append(chr(int(param, 16)))
                except ValueError:
                    pass
            continue
        if word.startswith("*"):
            if skip_stack:
                skip_stack[-1] = True
            continue
        if word in _DESTINATION_WORDS and fresh_stack and fresh_stack[-1]:
            skip_stack[-1] = True
            continue
        if word == "u":
            if not in_skip and param:
                try:
                    code = int(param)
                    if fresh_stack:
                        fresh_stack[-1] = False
                    out.append(chr(code))
                except ValueError:
                    pass
            pending_skip = uc_count
            continue
        if word == "uc":
            with contextlib.suppress(ValueError):
                uc_count = max(1, min(int(param), 4))
            continue
        if word in _PARAGRAPH_WORDS:
            if not in_skip:
                if fresh_stack:
                    fresh_stack[-1] = False
                out.append("\n")
            continue
        if word == "tab":
            if not in_skip:
                if fresh_stack:
                    fresh_stack[-1] = False
                out.append("\t")
            continue
    return "".join(out)


def _parse_control(text: str, i: int) -> tuple[str, str, int]:
    """Parse the backslash sequence at ``i`` into ``(word, param, next_index)``."""
    n = len(text)
    j = i + 1
    if j >= n:
        return "", "", n
    nxt = text[j]
    if nxt == "'":
        return "'", text[j + 1 : j + 3], min(j + 3, n)
    if nxt in "\\{}":
        return nxt, "", min(j + 1, n)
    chars: list[str] = []
    k = j
    if k < n and text[k] == "*":
        chars.append("*")
        k += 1
    while k < n and text[k].isalpha():
        chars.append(text[k])
        k += 1
    word = "".join(chars)
    param = ""
    if k < n and text[k] in "+-":
        param += text[k]
        k += 1
    while k < n and text[k].isdigit():
        param += text[k]
        k += 1
    if k < n and text[k] == " ":
        k += 1
    return word, param, k