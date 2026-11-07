# Alembic migration environment. Runs migrations against the same database
# the app uses (database.DATABASE_URL: the local SQLite file by default, or
# whatever DATABASE_URL is set to in a deployed environment).
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Make Backend/ importable no matter where `alembic` is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import models  # noqa: E402,F401  - registers every table on Base.metadata
from database import Base, engine  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade --sql)."""
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A test (or script) can hand in its own connection via
    # config.attributes["connection"]; otherwise use the app's engine.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with engine.connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most column/constraint changes in place;
        # batch mode makes Alembic copy-and-swap the table instead.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
