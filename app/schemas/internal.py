from datetime import date

from pydantic import BaseModel


class CleanupResponse(BaseModel):
    sessions_deleted: int


class DailyUsageEntry(BaseModel):
    day: date
    uploads: int
    questions: int


class UsageTotals(BaseModel):
    uploads: int
    questions: int
    days_with_activity: int


class ActiveSessions(BaseModel):
    count: int
    questions_in_progress: int


class StatsResponse(BaseModel):
    history: list[DailyUsageEntry]
    totals: UsageTotals
    active_sessions: ActiveSessions
