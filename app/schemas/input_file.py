import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InputFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime