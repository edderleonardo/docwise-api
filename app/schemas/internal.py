from pydantic import BaseModel


class CleanupResponse(BaseModel):
    sessions_deleted: int
