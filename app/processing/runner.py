import asyncio
import logging
import uuid

from sqlalchemy import update

from app.db.session import async_session_factory
from app.models.job import Job
from app.processing.service import ProcessingError, process_job
from app.storage import Storage, get_storage

logger = logging.getLogger(__name__)

_scheduled_tasks: set[asyncio.Task] = set()


def schedule_job(job_id: uuid.UUID, storage: Storage | None = None) -> None:
    """Fire-and-forget a processing run for ``job_id`` on the current loop.

    Temporary in-process adapter, intentionally isolated behind this module so
    a Redis/ARQ/Celery-backed worker can replace it later. The task owns its
    own DB session and storage; it never touches the request's session.
    """
    task = asyncio.create_task(_run_job(job_id, storage))
    _scheduled_tasks.add(task)
    task.add_done_callback(_scheduled_tasks.discard)
    task.add_done_callback(_log_unexpected_failure)


async def _run_job(job_id: uuid.UUID, storage: Storage | None) -> None:
    try:
        resolved = storage or get_storage()
        async with async_session_factory() as db:
            await process_job(job_id, db, resolved)
    except ProcessingError:
        logger.exception("processing failed for job %s", job_id)
    except Exception:
        logger.exception("unexpected processing error for job %s", job_id)
        await _ensure_not_stuck(job_id)


def _log_unexpected_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "scheduled processing task failed for %s",
            task,
            exc_info=(type(exc), exc, exc.__traceback__),
        )


async def _ensure_not_stuck(job_id: uuid.UUID) -> None:
    """Best-effort: if a job is still ``processing`` after an unexpected error, fail it."""
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "processing")
                .values(status="failed")
            )
            if result.rowcount == 1:
                await db.commit()
    except Exception:
        logger.exception("could not mark job %s as failed after unexpected error", job_id)