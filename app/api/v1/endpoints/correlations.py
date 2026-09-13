import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.services.correlation import CorrelationEngine
from app.storage.local import LocalStorage

router = APIRouter()


def get_storage() -> LocalStorage:
    config = Settings()
    return LocalStorage(base_dir=getattr(config, "STORAGE_DIR", getattr(config, "UPLOAD_DIR", "storage")))

@router.get("/transformations/{id}/correlations")
async def get_job_correlations(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    current_user: User = Depends(get_current_user),
):
    job = await db.scalar(
        select(Job).where(Job.id == id, Job.user_id == current_user.id)
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transformation job not found"
        )

    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == id, Artifact.artifact_type == "processing_result"
        )
    )
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing artifact missing"
        )

    try:
        content_bytes = storage.read(artifact.file_path)
        payload = json.loads(content_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read ground truth context",
        )

    engine = CorrelationEngine()
    graph_data = engine.build_graph(payload)

    return {
        "job_id": str(id),
        "correlation_graph": graph_data,
    }