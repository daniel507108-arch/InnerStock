"""per-user SnapTrade identities + disconnected brokerage accounts

  - snaptrade_users: one SnapTrade user (id + encrypted secret) per
    InnerStock user, for commercial/developer SnapTrade keys
  - brokerage_accounts.disconnected_at: marks accounts SnapTrade no longer
    reports, so their trades can be re-linked when the user reconnects

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "snaptrade_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("snaptrade_user_id", sa.String(), nullable=False),
        sa.Column("user_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("snaptrade_user_id"),
    )
    with op.batch_alter_table("brokerage_accounts") as batch_op:
        batch_op.add_column(sa.Column("disconnected_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("brokerage_accounts") as batch_op:
        batch_op.drop_column("disconnected_at")
    op.drop_table("snaptrade_users")
