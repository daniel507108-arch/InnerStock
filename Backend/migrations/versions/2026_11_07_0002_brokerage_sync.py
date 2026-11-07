"""brokerage sync: brokerage_accounts table + trade source/external_id

Adds what the SnapTrade (Wealthsimple) sync needs:
  - brokerage_accounts: one row per linked brokerage account
  - trades.source: where a trade came from ("manual" / "csv" / "snaptrade")
  - trades.external_id: the brokerage's id for the trade, unique per user,
    so re-syncing never creates duplicates
  - trades.brokerage_account_id: which linked account a synced trade is in

Existing trades are labelled from the one signal the old data has: CSV
imports never had a trade_time, manual trades always do.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brokerage_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("external_account_id", sa.String(), nullable=False),
        sa.Column("institution", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("account_type", sa.String(), nullable=True),
        sa.Column("sync_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "external_account_id", name="uq_brokerage_accounts_user_account"),
    )

    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(), server_default="manual", nullable=False))
        batch_op.add_column(sa.Column("external_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("brokerage_account_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_trades_brokerage_account_id", "brokerage_accounts", ["brokerage_account_id"], ["id"]
        )
        batch_op.create_unique_constraint("uq_trades_user_external_id", ["user_id", "external_id"])

    op.execute("UPDATE trades SET source = 'csv' WHERE trade_time IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_constraint("uq_trades_user_external_id", type_="unique")
        batch_op.drop_constraint("fk_trades_brokerage_account_id", type_="foreignkey")
        batch_op.drop_column("brokerage_account_id")
        batch_op.drop_column("external_id")
        batch_op.drop_column("source")
    op.drop_table("brokerage_accounts")
