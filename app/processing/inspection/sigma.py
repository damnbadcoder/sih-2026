import logging
from typing import Any

import yaml

from app.config import get_settings
from app.core.formats import MEDIA_CATEGORY_TEXT
from app.models.input_file import InputFile
from app.processing.inspection.base import BaseInspector, InspectionError
from app.processing.inspection.text import _decode_text, _read_bounded, flatten_json
from app.storage import Storage

logger = logging.getLogger(__name__)


class SigmaInspector(BaseInspector):
    """Sigma detection-rule inspector: ``yaml.safe_load`` + deterministic flatten.

    ``.sigma`` files are YAML detection rules treated strictly as configuration
    data. Only :func:`yaml.safe_load` is used (never ``yaml.load``), so no
    arbitrary object construction or tag execution is possible. The parsed
    document is flattened into the same deterministic ``key: value`` text lines
    used for JSON so downstream normalization and grounding see structured
    content. Malformed YAML becomes a controlled :class:`InspectionError`.
    """

    media_category = MEDIA_CATEGORY_TEXT
    supported_extensions = frozenset({".sigma"})
    supported_mime_types = frozenset({"text/yaml", "application/yaml"})

    async def _extract(
        self, file: InputFile, storage: Storage
    ) -> tuple[str | None, dict[str, Any]]:
        data, truncated = await _read_bounded(
            file, storage, get_settings().MAX_UPLOAD_SIZE_BYTES
        )
        text = _decode_text(data)
        if not text.strip():
            return None, {"format": "sigma", "char_count": 0, "truncated": truncated}
        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise InspectionError("sigma file is malformed or unreadable") from exc
        if value is None:
            return None, {"format": "sigma", "char_count": 0, "truncated": truncated}
        rendered = "\n".join(flatten_json(value))
        return (
            rendered or None,
            {"format": "sigma", "char_count": len(rendered), "truncated": truncated},
        )