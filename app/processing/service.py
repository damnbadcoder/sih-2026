import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.formats import classify_format
from app.models.artifact import Artifact
from app.models.input_file import InputFile
from app.models.job import Job
from app.processing.inspection import InspectionError, InspectionResult, get_inspector
from app.processing.normalization import (
    NORMALIZED_ARTIFACT_TYPE,
    build_normalized_records,
    normalized_artifact_max_bytes,
    serialize_normalized_records,
)
from app.storage import Storage, StorageError

logger = logging.getLogger(__name__)

PROCESSING_ARTIFACT_TYPE = "processing_result"
_ARTIFACT_MAX_BYTES = 1024 * 1024

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"processing"}),
    "processing": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}


class ProcessingError(Exception):
    """Base error raised by the processing service."""


class JobNotFoundError(ProcessingError):
    """Raised when the requested job does not exist."""


class NoInputFilesError(ProcessingError):
    """Raised when a job has no input files to process."""


class InvalidTransitionError(ProcessingError):
    """Raised when a job cannot move between the given statuses."""


@dataclass(frozen=True)
class ProcessingResult:
    """Outcome of a successful processing run."""

    job_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_type: str
    artifact_path: str
    input_file_count: int
    status: str = "completed"


def ensure_transition_allowed(current: str, target: str) -> None:
    """Validate a single job status transition against the allowed graph."""
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(
            f"cannot transition job status from {current!r} to {target!r}"
        )


async def reserve_job_for_processing(db: AsyncSession, job_id: uuid.UUID) -> Job:
    """Move a job from ``created`` to ``processing`` via an atomic claim.

    This is the single authoritative gate for starting a processing run.
    Exactly one caller can win the claim; any concurrent attempt sees an
    ``InvalidTransitionError``. Returns the freshly reserved job.
    """
    existing = await db.scalar(select(Job.id).where(Job.id == job_id))
    if existing is None:
        raise JobNotFoundError(f"job {job_id} does not exist")

    result = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "created")
        .values(status="processing")
    )
    if result.rowcount != 1:
        await db.rollback()
        current = await db.scalar(select(Job.status).where(Job.id == job_id))
        raise InvalidTransitionError(
            f"job {job_id} cannot start processing (current status: {current!r})"
        )
    await db.commit()

    job = await db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise JobNotFoundError(f"job {job_id} does not exist")
    return job


async def _load_input_files(db: AsyncSession, job_id: uuid.UUID) -> list[InputFile]:
    rows = await db.scalars(
        select(InputFile)
        .where(InputFile.job_id == job_id)
        .order_by(InputFile.created_at)
    )
    return list(rows)


def _verify_stored_files(storage: Storage, input_files: list[InputFile]) -> None:
    """Verify each stored input file resolves safely and matches its metadata."""
    for input_file in input_files:
        target = storage.resolve(input_file.storage_path)
        if not target.is_file():
            raise StorageError(f"stored input file missing: {input_file.storage_path}")
        if target.stat().st_size != input_file.file_size:
            raise StorageError(
                f"stored input file size mismatch: {input_file.storage_path}"
            )


async def _inspect_files(storage: Storage, input_files: list[InputFile]) -> list[InspectionResult]:
    """Classify every input file and inspect the ones with a registered inspector.

    Formats without an inspector are reported as unsupported at the
    application level; file-access failures are mapped to :class:`StorageError`
    so the job transitions to ``failed``.
    """
    inspections: list[InspectionResult] = []
    for input_file in input_files:
        classification = classify_format(input_file.original_filename, input_file.content_type)
        inspector = get_inspector(classification)
        if inspector is None:
            inspections.append(InspectionResult.unsupported(input_file, classification))
            continue
        try:
            inspections.append(await inspector.inspect(input_file, storage))
        except InspectionError as exc:
            raise StorageError(
                f"input file inspection failed: {input_file.storage_path}"
            ) from exc
    return inspections


async def _chunks_of(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _build_artifact_content(
    job: Job,
    input_files: list[InputFile],
    inspections: list[InspectionResult],
) -> bytes:
    payload = {
        "artifact_type": PROCESSING_ARTIFACT_TYPE,
        "job_id": str(job.id),
        "status": "completed",
        "input_file_count": len(input_files),
        "input_files": [
            {"original_filename": f.original_filename, "file_size": f.file_size}
            for f in input_files
        ],
        "inspected_files": [
            {
                "original_filename": result.original_filename,
                "media_category": result.media_category,
                "supported_for_inspection": result.supported_for_inspection,
                "extracted_chars": (
                    len(result.extracted_text) if result.extracted_text is not None else None
                ),
                "metadata": result.metadata,
            }
            for result in inspections
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return (json.dumps(payload, indent=2) + "\n").encode()


async def _set_failed(db: AsyncSession, job_id: uuid.UUID) -> None:
    ensure_transition_allowed("processing", "failed")
    await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "processing")
        .values(status="failed")
    )
    await db.commit()


async def _complete_job(
    db: AsyncSession,
    storage: Storage,
    job_id: uuid.UUID,
    artifact_paths: list[tuple[str, str]],
) -> Artifact:
    """Mark a processing job completed and persist all its artifacts atomically.

    ``artifact_paths`` is a list of ``(artifact_type, file_path)`` pairs. The
    first entry is the primary artifact returned to callers. All rows are
    committed in the same transaction as the status transition; on any failure
    every freshly written artifact file is removed and the job is failed.
    """
    artifacts = [
        Artifact(job_id=job_id, artifact_type=artifact_type, file_path=path)
        for artifact_type, path in artifact_paths
    ]
    db.add_all(artifacts)
    ensure_transition_allowed("processing", "completed")
    try:
        result = await db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "processing")
            .values(status="completed")
        )
        if result.rowcount != 1:
            raise InvalidTransitionError(f"job {job_id} could not be marked completed")
        await db.commit()
    except Exception as exc:
        await db.rollback()
        for _, artifact_path in artifact_paths:
            try:
                await storage.delete(artifact_path)
            except StorageError:
                logger.warning(
                    "failed to remove orphaned artifact %s after DB failure",
                    artifact_path,
                    exc_info=True,
                )
        try:
            await _set_failed(db, job_id)
        except Exception:
            logger.exception("failed to persist failed status for job %s", job_id)
        raise ProcessingError(f"processing failed for job {job_id}") from exc
    await db.refresh(artifacts[0])
    return artifacts[0]


async def process_job(job_id: uuid.UUID, db: AsyncSession, storage: Storage) -> ProcessingResult:
    """Process a job that has already been reserved (status ``processing``).

    Call ``reserve_job_for_processing`` first; this function continues the
    run from a reserved job and transitions it to ``completed`` (or ``failed``).
    ``db`` and ``storage`` are injected so a future queue worker can own their
    lifecycle.
    """
    job = await db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise JobNotFoundError(f"job {job_id} does not exist")
    if job.status != "processing":
        raise InvalidTransitionError(
            f"job {job_id} cannot be processed (current status: {job.status!r})"
        )
    input_files = await _load_input_files(db, job_id)

    if not input_files:
        await _set_failed(db, job_id)
        raise NoInputFilesError(f"job {job_id} has no input files")

    try:
        _verify_stored_files(storage, input_files)
        inspections = await _inspect_files(storage, input_files)
    except StorageError as exc:
        await _set_failed(db, job_id)
        logger.exception("input file inspection failed for job %s", job_id)
        raise ProcessingError(
            "processing failed: stored input files could not be verified"
        ) from exc

    artifact_paths: list[tuple[str, str]] = []
    summary_path = f"{job.user_id}/{job_id}/artifacts/{uuid.uuid4().hex}.json"
    content = _build_artifact_content(job, input_files, inspections)
    normalized_path = f"{job.user_id}/{job_id}/artifacts/{uuid.uuid4().hex}.json"
    records = build_normalized_records(inspections)
    try:
        await storage.save(_chunks_of(content), summary_path, max_size=_ARTIFACT_MAX_BYTES)
        artifact_paths.append((PROCESSING_ARTIFACT_TYPE, summary_path))

        await storage.save(
            serialize_normalized_records(records),
            normalized_path,
            max_size=normalized_artifact_max_bytes(len(records)),
        )
        artifact_paths.append((NORMALIZED_ARTIFACT_TYPE, normalized_path))
    except StorageError as exc:
        for _, artifact_path in artifact_paths:
            try:
                await storage.delete(artifact_path)
            except StorageError:
                logger.warning(
                    "failed to remove orphaned artifact %s after write failure",
                    artifact_path,
                    exc_info=True,
                )
        await _set_failed(db, job_id)
        logger.exception("artifact write failed for job %s", job_id)
        raise ProcessingError("processing failed: could not write artifacts") from exc

    artifact = await _complete_job(db, storage, job_id, artifact_paths)
    return ProcessingResult(
        job_id=job_id,
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        artifact_path=artifact.file_path,
        input_file_count=len(input_files),
    )