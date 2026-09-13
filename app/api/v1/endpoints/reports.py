import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_storage
from app.db.session import get_db
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.processing.reports.pdf import generate_forensic_pdf
from app.storage import Storage

router = APIRouter()


@router.get("/jobs/{job_id}/report/pdf")
async def get_job_pdf_report(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
):
    job = await db.scalar(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot generate report for job in state '{job.status}'",
        )

    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job_id, Artifact.artifact_type == "processing_result"
        )
    )
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job summary artifact missing"
        )

    content_bytes = storage.read(artifact.file_path)
    payload = json.loads(content_bytes.decode("utf-8"))

    pdf_bytes = generate_forensic_pdf(
        job_id=str(job_id),
        overall_tlp=payload.get("overall_tlp", "TLP:CLEAR"),
        inspected_files=payload.get("inspected_files", []),
        timeline_events=payload.get("timeline", []),
        artifact_hash=artifact.file_path,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="forensic_report_{job_id.hex[:8]}.pdf"'
        },
    )