"""grading snapshot: trades.graded_at, suggested_outcome, graded_return_pct, graded_benchmark_return_pct

Trades graded before this have no snapshot (the numbers weren't recorded
at the time), so these stay NULL for them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(sa.Column("graded_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("suggested_outcome", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("graded_return_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("graded_benchmark_return_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_column("graded_benchmark_return_pct")
        batch_op.drop_column("graded_return_pct")
        batch_op.drop_column("suggested_outcome")
        batch_op.drop_column("graded_at")
