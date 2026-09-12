import contextlib
import io
import logging
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from docx import Document
from pptx import Presentation

from app.core.formats import MEDIA_CATEGORY_DOCUMENT, MEDIA_CATEGORY_PRESENTATION
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError, stream_to_buffer
from app.processing.inspection.pptx import _MAX_PPTX_TEXT_CHARS, _slide_text_lines
from app.storage import Storage

logger = logging.getLogger(__name__)

_DOC_MIME_TYPE = "application/msword"
_PPT_MIME_TYPE = "application/vnd.ms-powerpoint"

# Every legacy .doc/.ppt file is an OLE2 compound document; this is a strict,
# unambiguous structural gate checked before LibreOffice ever sees the bytes.
_OLE2_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_CONVERSION_TIMEOUT_SECONDS = 60
_HEADLESS_ARGS = (
    "--headless",
    "--norestore",
    "--nolockcheck",
    "--nodefault",
    "--nologo",
    "--nofirststartwizard",
)


class _OfficeConversionError(ValueError):
    """Internal signal: headless LibreOffice could not produce a safe output."""


def _libreoffice_binary() -> str | None:
    for candidate in ("soffice", "libreoffice", "/usr/bin/soffice", "/usr/bin/libreoffice"):
        resolved = shutil.which(candidate) or (
            candidate if os.path.isfile(candidate) else None
        )
        if resolved and os.path.isfile(resolved):
            return resolved
    return None


def _convert_with_libreoffice(source: Any, target_ext: str) -> bytes:
    """Convert untrusted legacy Office bytes to an OOXML package via headless LibreOffice.

    The uploaded bytes are copied into a freshly created, randomly named
    workspace under a fixed input basename; the caller's filename never reaches
    the subprocess, so client input cannot influence the command line or the
    output path. LibreOffice runs fully headless with a throwaway profile
    (``-env:UserInstallation``) inside that workspace: it never opens a GUI,
    never loads saved user configuration, and never executes document macros or
    scripts during a filter conversion. The converted package is read back into
    memory and the entire workspace is destroyed.

    Structural validation is done here and only here: the source must start
    with the OLE2 signature and LibreOffice must actually produce a converted
    file. Anything else becomes a controlled failure.
    """
    binary = _libreoffice_binary()
    if binary is None:
        raise _OfficeConversionError("LibreOffice is not installed in this runtime")

    with tempfile.TemporaryDirectory(prefix="office_inspect_") as workdir:
        work = Path(workdir)
        src_path = work / "input"
        with open(src_path, "wb") as out:
            shutil.copyfileobj(source, out)
            out.flush()
        if src_path.read_bytes()[:8] != _OLE2_SIGNATURE:
            raise _OfficeConversionError("legacy Office OLE2 signature missing")
        source.seek(0)

        outdir = work / "out"
        outdir.mkdir()
        profile = work / "profile"
        profile.mkdir()
        env = os.environ.copy()
        env["HOME"] = str(work)
        env["TMPDIR"] = str(work)

        cmd = [
            binary,
            *_HEADLESS_ARGS,
            "-env:UserInstallation=file://" + profile.as_posix(),
            "--convert-to",
            target_ext,
            "--outdir",
            str(outdir),
            str(src_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=_CONVERSION_TIMEOUT_SECONDS,
                start_new_session=True,
                env=env,
            )
        except subprocess.TimeoutExpired:
            logger.warning("LibreOffice conversion timed out for an uploaded file")
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
            raise _OfficeConversionError("LibreOffice conversion timed out") from None
        except OSError as exc:
            raise _OfficeConversionError("LibreOffice could not be started") from exc

        converted = outdir / f"input.{target_ext}"
        if proc.returncode != 0 or not converted.is_file():
            logger.warning(
                "LibreOffice conversion failed (rc=%s) for an uploaded file",
                proc.returncode,
            )
            raise _OfficeConversionError("LibreOffice produced no converted output")
        return converted.read_bytes()


class DOCInspector(BaseInspector):
    """Legacy binary Word (``.doc``) inspector: real paragraph-text extraction.

    The bytes are validated as an OLE2 compound document and converted to
    ``.docx`` by LibreOffice in headless, macro-exempt mode; the converted
    package is parsed with ``python-docx`` exactly like :class:`DOCXInspector`.
    No macros, scripts, OLE objects or embedded active content are executed.
    """

    media_category = MEDIA_CATEGORY_DOCUMENT
    supported_extensions = frozenset({".doc"})
    supported_mime_types = frozenset({_DOC_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                converted = _convert_with_libreoffice(buffer, "docx")
                document = Document(io.BytesIO(converted))
                paragraphs = [paragraph.text for paragraph in document.paragraphs]
            except Exception as exc:
                raise InspectionError("DOC file is malformed or unreadable") from exc
        finally:
            buffer.close()

        text = "\n".join(paragraphs).strip()
        return (text or None), {
            "format": "doc",
            "converted_via": "libreoffice",
            "paragraph_count": len(paragraphs),
            "char_count": len(text),
        }


class PPTInspector(BaseInspector):
    """Legacy binary PowerPoint (``.ppt``) inspector: real slide-text extraction.

    The bytes are validated as an OLE2 compound document and converted to
    ``.pptx`` by LibreOffice in headless, macro-exempt mode; the converted
    package is parsed with ``python-pptx`` exactly like :class:`PPTXInspector`.
    No macros, scripts, OLE objects or embedded active content are executed.
    """

    media_category = MEDIA_CATEGORY_PRESENTATION
    supported_extensions = frozenset({".ppt"})
    supported_mime_types = frozenset({_PPT_MIME_TYPE})

    async def _extract(self, file: InputFile, storage: Storage):
        buffer = await stream_to_buffer(file, storage)
        try:
            try:
                converted = _convert_with_libreoffice(buffer, "pptx")
                presentation = Presentation(io.BytesIO(converted))
            except Exception as exc:
                raise InspectionError("PPT file is malformed or unreadable") from exc
        finally:
            buffer.close()

        slide_count = len(presentation.slides)
        lines: list[str] = []
        total = 0
        truncated = False
        for slide in presentation.slides:
            for line in _slide_text_lines(slide):
                lines.append(line)
                total += len(line)
                if total >= _MAX_PPTX_TEXT_CHARS:
                    truncated = True
                    break
            if truncated:
                break
        text = "\n".join(lines).strip()
        return (text or None), {
            "format": "ppt",
            "converted_via": "libreoffice",
            "slide_count": slide_count,
            "char_count": total,
            "truncated": truncated,
        }