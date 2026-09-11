"""Application-level grounding adapter (thin, no new infrastructure).

The boundary is:

    source inputs
      -> Stage 12 inspection (get_inspector + InspectionResult)
      -> Stage 13 normalization (iter_normalized_records)
      -> pipeline-specific deterministic extraction (IOCExtractor,
         build_llm_injection_bundle) reused verbatim from pipelines
      -> normalized grounding context (GroundedSource / GroundingContext)
      -> future blueprint & deliverable generation services

No vector store, no embeddings, no generic RAG, no network fetching, and no
duplication of the pipeline IOC regexes: the existing extractor is imported
directly.  LLM grounding anchors (``EnrichedGroundingContext``) require the
unprovisioned Groq interpreter and are deliberately **not** produced here;
the adapter stops at the deterministic normalized context.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.core.formats import MEDIA_CATEGORY_TEXT, classify_format
from app.models.transformation import Transformation
from app.models.transformation_source import TransformationSource
from app.processing.inspection import InspectionError, InspectionResult, get_inspector
from app.processing.normalization import iter_normalized_records
from app.schemas.grounding import GroundedSource, GroundingContext
from app.storage import Storage, StorageError, get_storage
from pipelines.text_pipeline.chunking import build_llm_injection_bundle, estimate_tokens
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor
from pipelines.text_pipeline.schema import DocumentMetadata, ExtractedIOCs

_IOC_KEYS: list[str] = [
    "cve",
    "mitre",
    "ipv4",
    "ipv6",
    "sha256",
    "sha1",
    "md5",
    "domains",
    "urls",
]


def _iocs_to_dict(iocs: ExtractedIOCs) -> dict[str, list[str]]:
    return {
        "cve": list(iocs.cves),
        "mitre": list(iocs.mitre_attack_ids),
        "ipv4": list(iocs.ipv4_addresses),
        "ipv6": list(iocs.ipv6_addresses),
        "sha256": list(iocs.sha256_hashes),
        "sha1": list(iocs.sha1_hashes),
        "md5": list(iocs.md5_hashes),
        "domains": list(iocs.domains),
        "urls": list(iocs.urls),
    }


def _aggregate(grounded: list[GroundedSource]) -> dict[str, list[str]]:
    aggregated: dict[str, set[str]] = {key: set() for key in _IOC_KEYS}
    for source in grounded:
        for key in _IOC_KEYS:
            aggregated[key].update(source.iocs.get(key, []))
    return {key: sorted(values) for key, values in aggregated.items()}


def _document_metadata(
    label: str,
    record_type: str,
    text: str,
    size_bytes: int,
) -> DocumentMetadata:
    return DocumentMetadata(
        file_name=label or "inline-text",
        file_path="",
        file_type=record_type or "text",
        file_size_bytes=size_bytes,
        sha256_checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        word_count=len(text.split()),
        character_count=len(text),
        estimated_tokens=estimate_tokens(text),
        line_count=max(1, text.count("\n") + 1),
    )


class GroundingService:
    """Assembles the deterministic normalized grounding context."""

    def __init__(self, storage: Storage | None = None) -> None:
        self._storage = storage or get_storage()
        self._extractor = IOCExtractor()

    async def build_context(
        self,
        transformation: Transformation,
    ) -> GroundingContext:
        grounded: list[GroundedSource] = []
        for source in transformation.sources:
            grounded.append(await self._ground_source(source))
        return GroundingContext(
            transformation_id=transformation.id,
            sources=grounded,
            indicators=_aggregate(grounded),
            ioc_extraction_available=True,
            generated_at=datetime.now(UTC),
        )

    async def _ground_source(self, source: TransformationSource) -> GroundedSource:
        record = await self._normalized_record(source)
        normalized = record.get("normalized_text")
        if record.get("supported_for_inspection") is not True or not normalized:
            return self._ground_without_text(source, record)
        return self._ground_with_text(source, record, normalized)

    async def _normalized_record(self, source: TransformationSource) -> dict[str, Any]:
        if source.source_type == "url":
            return {
                "input_file_id": str(source.id),
                "original_filename": source.label or "external-url",
                "media_category": None,
                "extension": None,
                "supported_for_inspection": False,
                "normalized_text": None,
                "truncated": False,
                "reason": "URL ingestion never fetches content; policy decision recorded",
            }
        if source.source_type == "text":
            result = InspectionResult(
                input_file_id=source.id,
                original_filename=source.label or "inline-text",
                media_category=MEDIA_CATEGORY_TEXT,
                content_type="text/plain",
                file_size=len((source.text_content or "").encode("utf-8")),
                extension=None,
                supported_for_inspection=True,
                extracted_text=source.text_content,
            )
            return list(iter_normalized_records([result]))[0]
        return await self._normalized_file_record(source)

    async def _normalized_file_record(self, source: TransformationSource) -> dict[str, Any]:
        input_file = source.input_file
        if input_file is None:
            return {
                "input_file_id": str(source.id),
                "original_filename": source.label or "missing-file",
                "media_category": None,
                "extension": None,
                "supported_for_inspection": False,
                "normalized_text": None,
                "truncated": False,
                "reason": "attached input file is not available",
            }
        classification = classify_format(input_file.original_filename, input_file.content_type)
        inspector = get_inspector(classification)
        try:
            if inspector is None:
                result = InspectionResult.unsupported(input_file, classification)
            else:
                result = await inspector.inspect(input_file, self._storage)
        except (InspectionError, StorageError):
            return {
                "input_file_id": str(input_file.id),
                "original_filename": input_file.original_filename,
                "media_category": classification.media_category,
                "extension": classification.extension,
                "supported_for_inspection": False,
                "normalized_text": None,
                "truncated": False,
                "reason": "inspection failed or file could not be read",
            }
        return list(iter_normalized_records([result]))[0]

    def _ground_without_text(
        self, source: TransformationSource, record: dict[str, Any]
    ) -> GroundedSource:
        metadata: dict[str, Any] = {
            "media_category": record.get("media_category"),
            "extension": record.get("extension"),
        }
        if source.source_metadata:
            metadata.update(source.source_metadata)
        return GroundedSource(
            source_id=source.id,
            source_type=source.source_type,
            label=source.label,
            media_category=record.get("media_category"),
            normalized_text=None,
            truncated=False,
            reason=record.get("reason") or "no extractable text",
            iocs={},
            metadata=metadata,
        )

    def _ground_with_text(
        self,
        source: TransformationSource,
        record: dict[str, Any],
        normalized: str,
    ) -> GroundedSource:
        iocs = self._extractor.extract_iocs(normalized)
        threat_intel = self._extractor.extract_threat_summary(normalized)
        bundle = build_llm_injection_bundle(
            metadata=_document_metadata(
                label=source.label or record.get("original_filename") or "inline-text",
                record_type=str(record.get("extension") or "text"),
                text=normalized,
                size_bytes=int(record.get("normalized_char_count") or len(normalized)),
            ),
            clean_markdown=normalized,
            iocs=iocs,
            tables=[],
            threat_intel=threat_intel,
        )
        metadata: dict[str, Any] = {
            "media_category": record.get("media_category"),
            "extension": record.get("extension"),
            "extracted_chars": record.get("normalized_char_count"),
            "truncated": record.get("truncated", False),
            "ioc_total": iocs.total_iocs_found,
            "threat_intel": threat_intel.model_dump(),
            "grounding_header": bundle.system_grounding_header,
            "chunk_count": len(bundle.semantic_chunks),
        }
        return GroundedSource(
            source_id=source.id,
            source_type=source.source_type,
            label=source.label,
            media_category=record.get("media_category"),
            normalized_text=normalized,
            truncated=bool(record.get("truncated", False)),
            reason=None,
            iocs=_iocs_to_dict(iocs),
            metadata=metadata,
        )


__all__ = ["GroundingService", "GroundedSource", "GroundingContext"]