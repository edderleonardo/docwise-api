"""Embedding column to 768 dims (Gemini embeddings API)

Existing chunks hold 384-dim MiniLM vectors, incompatible with the new
gemini-embedding-001 vectors. Sessions are ephemeral by design (24h TTL),
so we wipe them instead of re-embedding.

Revision ID: b3f7a9d21c40
Revises: 6c2a5561e639
Create Date: 2026-07-03

"""

from typing import Sequence, Union

import pgvector
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f7a9d21c40"
down_revision: Union[str, Sequence[str], None] = "6c2a5561e639"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Old 384-dim vectors can't be cast to 768 — drop all sessions
    # (chunks cascade). Sessions are ephemeral, nothing of value is lost.
    op.execute("DELETE FROM sessions")
    op.alter_column(
        "chunks",
        "embedding",
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
        existing_nullable=False,
        postgresql_using="embedding::vector(768)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM sessions")
    op.alter_column(
        "chunks",
        "embedding",
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=384),
        existing_nullable=False,
        postgresql_using="embedding::vector(384)",
    )
