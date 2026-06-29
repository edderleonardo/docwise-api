import uuid
from datetime import datetime
from pydantic import BaseModel


class UploadResponse(BaseModel):
    session_id: uuid.UUID
    filename: str
    status: str
    chunk_count: int
    message: str


class StatusResponse(BaseModel):
    session_id: uuid.UUID
    filename: str
    status: str
    questions_used: int
    max_questions: int
    created_at: datetime
    last_activity: datetime


class DeleteResponse(BaseModel):
    message: str
    session_id: uuid.UUID
