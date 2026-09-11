import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    artifact_type: str
    file_path: str
    created_at: datetime