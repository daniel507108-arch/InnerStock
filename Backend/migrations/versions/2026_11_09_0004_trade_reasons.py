"""trade reasons: trades.reason_tags + trades.thesis_written_at

Existing trades that already have a thesis were written when they were
logged, so thesis_written_at is backfilled from created_at.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(sa.Column("reason_tags", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("thesis_written_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE trades SET thesis_written_at = created_at WHERE thesis_text IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_column("thesis_written_at")
        batch_op.drop_column("reason_tags")
