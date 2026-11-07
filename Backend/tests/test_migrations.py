# Tests for the Alembic migrations in migrations/versions/.
#
# 1. A fresh database migrated to head must match models.py exactly - this
#    catches a model change that was made without adding a migration.
# 2. A database from before Alembic existed (built by the old create_all,
#    possibly from older models) must upgrade in place without losing data.
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from database import Base

BACKEND_DIR = Path(__file__).resolve().parent.parent


def upgrade(engine, revision="head"):
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield engine
    engine.dispose()


def test_fresh_database_matches_models(engine):
    upgrade(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"models.py and migrations disagree - add a migration: {diff}"


def test_pre_alembic_database_upgrades_without_losing_data(engine):
    # An old-style database: tables created by create_all from an older
    # version of the models (no trade_time/review_notes columns yet, no
    # watchlist table), with real rows in it.
    with engine.begin() as connection:
        connection.execute(sa.text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
            "email VARCHAR NOT NULL, hashed_password VARCHAR NOT NULL, created_at DATETIME)"
        ))
        connection.execute(sa.text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        connection.execute(sa.text(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
            "ticker VARCHAR NOT NULL, action VARCHAR NOT NULL, quantity NUMERIC NOT NULL, "
            "price_per_share NUMERIC NOT NULL, trade_date DATE NOT NULL, thesis_text TEXT, "
            "conviction_score INTEGER, review_date DATE, outcome_tag VARCHAR, created_at DATETIME)"
        ))
        connection.execute(sa.text("INSERT INTO users (id, name, email, hashed_password) VALUES (1, 'A', 'a@x.com', 'h')"))
        connection.execute(sa.text(
            "INSERT INTO trades (user_id, ticker, action, quantity, price_per_share, trade_date, thesis_text) "
            "VALUES (1, 'VFV.TO', 'buy', 10, 150, '2026-03-02', 'kept')"
        ))

    upgrade(engine)

    inspector = sa.inspect(engine)
    assert "watchlist" in inspector.get_table_names()
    assert "brokerage_accounts" in inspector.get_table_names()
    trade_columns = {c["name"] for c in inspector.get_columns("trades")}
    assert {"trade_time", "review_notes", "source", "external_id", "brokerage_account_id"} <= trade_columns

    with engine.connect() as connection:
        row = connection.execute(sa.text("SELECT ticker, thesis_text, source FROM trades")).one()
    # No trade_time on an old row means it came from the CSV import.
    assert tuple(row) == ("VFV.TO", "kept", "csv")


def test_upgrade_is_repeatable(engine):
    upgrade(engine)
    upgrade(engine)  # already at head - must be a no-op, not an error
