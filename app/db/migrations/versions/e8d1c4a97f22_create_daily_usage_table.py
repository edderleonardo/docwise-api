"""Create daily_usage table (global abuse/cost budget counters)

One row per day. Upload and chat endpoints atomically upsert-increment
their counter and the API answers 503 once the configured daily budget
is exhausted — a hard cap on the worst-case Gemini bill.

Revision ID: e8d1c4a97f22
Revises: b3f7a9d21c40
Create Date: 2026-07-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8d1c4a97f22"
down_revision: Union[str, Sequence[str], None] = "b3f7a9d21c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "daily_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("uploads", sa.Integer(), nullable=False),
        sa.Column("questions", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("daily_usage")
