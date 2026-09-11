import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User
from app.processing import InvalidTransitionError, reserve_job_for_processing
from app.processing.runner import schedule_job
from app.schemas.job import JobCreateRequest, JobDetailResponse, JobResponse, ProcessJobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    job = Job(user_id=current_user.id, status="created", config=payload.config)
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create job",
        ) from None
    await db.refresh(job)
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobDetailResponse:
    job = await db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.input_files), selectinload(Job.artifacts))
    )
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    job.input_files.sort(key=lambda f: f.created_at)
    job.artifacts.sort(key=lambda a: a.created_at)
    return JobDetailResponse.model_validate(job)


@router.post(
    "/{job_id}/process",
    response_model=ProcessJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_job_processing(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessJobResponse:
    row = (await db.execute(select(Job.id, Job.user_id).where(Job.id == job_id))).first()
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        await reserve_job_for_processing(db, job_id)
    except InvalidTransitionError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Job cannot be processed in its current state",
        ) from None

    schedule_job(job_id)
    return ProcessJobResponse(job_id=job_id, status="processing")