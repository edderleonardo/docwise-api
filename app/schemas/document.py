import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UploadResponse(BaseModel):
    session_id: uuid.UUID
    filename: str
    status: str
    chunk_count: int
    message: str


class StatusResponse(BaseModel):
    # Built from the Session ORM object, whose PK is `id`
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    session_id: uuid.UUID = Field(validation_alias="id")
    filename: str
    status: str
    questions_used: int
    max_questions: int
    created_at: datetime
    last_active: datetime


class DeleteResponse(BaseModel):
    message: str
    session_id: uuid.UUID
