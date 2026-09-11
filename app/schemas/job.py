import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.artifact import ArtifactResponse
from app.schemas.input_file import InputFileResponse


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any] | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class JobDetailResponse(JobResponse):
    input_files: list[InputFileResponse] = []
    artifacts: list[ArtifactResponse] = []


class ProcessJobResponse(BaseModel):
    job_id: uuid.UUID
    status: str