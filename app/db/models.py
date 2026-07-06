import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing"
    )  # processing | ready | expired
    questions_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        # Lambda so the configured value is read per session, not at import time
        default=lambda: settings.max_questions,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Relation with Document (Chunks), if session is deleted, all chunks will be deleted as well
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dims),
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="chunks",
    )


class DailyUsage(Base):
    """
    Global per-day counters used as a cost brake: once the daily budget of
    uploads or questions is spent, the API answers 503 until the next day.
    This bounds the worst-case Gemini bill regardless of how many IPs an
    attacker rotates through.
    """

    __tablename__ = "daily_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    uploads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
