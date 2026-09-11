import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.uploads import UploadValidationError, normalize_filename, validate_upload_type
from app.db.session import get_db
from app.models.input_file import InputFile
from app.models.job import Job
from app.models.user import User
from app.schemas.input_file import InputFileResponse
from app.storage import Storage, StorageError, UploadTooLargeError, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["uploads"])

_single_megabyte = 1024 * 1024


async def _iter_upload_chunks(
    file: UploadFile, chunk_size: int = _single_megabyte
) -> AsyncIterator[bytes]:
    while chunk := await file.read(chunk_size):
        yield chunk


@router.post(
    "/{job_id}/input",
    response_model=InputFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_input_file(
    job_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> InputFileResponse:
    job = await db.scalar(select(Job).where(Job.id == job_id))
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")

    original_filename = normalize_filename(file.filename or "")
    try:
        content_type, extension = validate_upload_type(original_filename, file.content_type)
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from None

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    storage_path = f"{job.user_id}/{job.id}/input/{stored_filename}"

    try:
        file_size = await storage.save(
            _iter_upload_chunks(file),
            storage_path,
            max_size=get_settings().MAX_UPLOAD_SIZE_BYTES,
        )
    except UploadTooLargeError:
        max_size = get_settings().MAX_UPLOAD_SIZE_BYTES
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {max_size} bytes",
        ) from None
    except StorageError:
        logger.exception("storage failure while saving upload for job %s", job.id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store file"
        ) from None
    finally:
        await file.close()

    input_file = InputFile(
        job_id=job.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_size=file_size,
        storage_path=storage_path,
    )
    db.add(input_file)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            await storage.delete(storage_path)
        except StorageError:
            logger.exception(
                "failed to remove orphaned stored file %s after DB failure", storage_path
            )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store file"
        ) from None
    await db.refresh(input_file)
    return InputFileResponse.model_validate(input_file)