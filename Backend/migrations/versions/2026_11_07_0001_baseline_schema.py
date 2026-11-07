"""baseline schema

The schema as it stood when Alembic was introduced (everything init_db.py's
create_all used to build).

Written to be safe on databases that already exist, because every developer
has a local innerstock.db that was created by create_all before migrations
existed - possibly from an older version of the models:
  - a table that doesn't exist yet is created in full
  - a table that already exists only gets the columns it's missing
    (added as nullable, since existing rows have no value for them)
So `alembic upgrade head` works the same on a brand-new database and on an
old one, and nobody has to delete their data.

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamp(name):
    return sa.Column(name, sa.DateTime(), server_default=sa.func.now(), nullable=True)


def _tables():
    return {
        "users": [
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            _timestamp("created_at"),
            sa.PrimaryKeyConstraint("id"),
        ],
        "price_cache": [
            sa.Column("ticker", sa.String(), nullable=False),
            sa.Column("current_price", sa.Numeric(), nullable=False),
            sa.Column("previous_close", sa.Numeric(), nullable=True),
            sa.Column("market_cap", sa.Numeric(), nullable=True),
            sa.Column("pe_ratio", sa.Numeric(), nullable=True),
            sa.Column("sector", sa.String(), nullable=True),
            sa.Column("forward_pe", sa.Numeric(), nullable=True),
            sa.Column("price_to_book", sa.Numeric(), nullable=True),
            sa.Column("profit_margins", sa.Numeric(), nullable=True),
            sa.Column("revenue_growth", sa.Numeric(), nullable=True),
            sa.Column("debt_to_equity", sa.Numeric(), nullable=True),
            sa.Column("dividend_yield", sa.Numeric(), nullable=True),
            _timestamp("last_updated"),
            sa.PrimaryKeyConstraint("ticker"),
        ],
        "sentiment_cache": [
            sa.Column("ticker", sa.String(), nullable=False),
            sa.Column("sentiment", sa.String(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            _timestamp("last_updated"),
            sa.PrimaryKeyConstraint("ticker"),
        ],
        "chat_messages": [
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            _timestamp("created_at"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        ],
        "trades": [
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("quantity", sa.Numeric(), nullable=False),
            sa.Column("price_per_share", sa.Numeric(), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("trade_time", sa.Time(), nullable=True),
            sa.Column("thesis_text", sa.Text(), nullable=True),
            sa.Column("conviction_score", sa.Integer(), nullable=True),
            sa.Column("review_date", sa.Date(), nullable=True),
            sa.Column("outcome_tag", sa.String(), nullable=True),
            sa.Column("review_notes", sa.Text(), nullable=True),
            _timestamp("created_at"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        ],
        "user_profiles": [
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("risk_tolerance", sa.String(), nullable=False),
            sa.Column("investing_goals", sa.String(), nullable=False),
            sa.Column("trading_style", sa.String(), nullable=False),
            sa.Column("time_horizon", sa.String(), nullable=False),
            sa.Column("income_bracket", sa.String(), nullable=False),
            sa.Column("experience_level", sa.String(), nullable=False),
            sa.Column("sectors_of_interest", sa.String(), nullable=False),
            sa.Column("biggest_fear", sa.Text(), nullable=True),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        ],
        "watchlist": [
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(), nullable=False),
            _timestamp("added_at"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
        ],
    }


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    for table_name, elements in _tables().items():
        if table_name not in existing_tables:
            op.create_table(table_name, *elements)
            continue

        # Table exists from the pre-Alembic create_all days - only fill in
        # columns an older version of the models didn't have yet.
        existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
        missing = [e for e in elements if isinstance(e, sa.Column) and e.name not in existing_columns]
        if missing:
            with op.batch_alter_table(table_name) as batch_op:
                for column in missing:
                    # Nullable and without a server default: SQLite can't add
                    # a NOT NULL column or a CURRENT_TIMESTAMP default to a
                    # table that already has rows.
                    batch_op.add_column(sa.Column(column.name, column.type, nullable=True))

    existing_indexes = {i["name"] for i in inspector.get_indexes("users")} if "users" in existing_tables else set()
    if "ix_users_email" not in existing_indexes:
        op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    for table_name in ["watchlist", "user_profiles", "trades", "chat_messages", "sentiment_cache", "price_cache", "users"]:
        op.drop_table(table_name)
