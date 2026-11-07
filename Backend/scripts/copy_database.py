"""Copy every row from one InnerStock database into another.

Built for moving the local SQLite database into hosted Postgres before
deploying, but works between any two databases SQLAlchemy supports.

Usage (from Backend/):
    python scripts/copy_database.py

Reads two settings from the environment / Backend/.env:
    SOURCE_DATABASE_URL   where to copy FROM (default: the local innerstock.db)
    TARGET_DATABASE_URL   where to copy TO, e.g. the Neon/Postgres URL

TARGET_DATABASE_URL is deliberately a separate variable from DATABASE_URL:
putting the hosted URL in DATABASE_URL would point your local app at the
production database.

What it does:
  1. checks the source is fully migrated
  2. runs all Alembic migrations on the target (creating the tables)
  3. refuses to continue if the target already has data (no overwrites)
  4. copies every table in foreign-key order, keeping the same ids
  5. on Postgres, moves each id sequence past the copied ids so new rows
     don't collide with them
  6. compares row counts table by table
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)  # so the default sqlite:///./innerstock.db resolves to Backend/

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

import models  # noqa: E402,F401  - registers every table on Base.metadata
from database import Base, normalize_database_url  # noqa: E402

BATCH_SIZE = 500


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def current_revision(engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def describe(url: str) -> str:
    """URL with the password hidden, safe to print."""
    return sa.engine.make_url(url).render_as_string(hide_password=True)


def main() -> int:
    source_url = normalize_database_url(os.getenv("SOURCE_DATABASE_URL") or "sqlite:///./innerstock.db")
    target_url = normalize_database_url(os.getenv("TARGET_DATABASE_URL") or "")
    if not target_url:
        print("Set TARGET_DATABASE_URL (in Backend/.env or the environment) to the database to copy into.")
        return 1
    if source_url == target_url:
        print("Source and target are the same database - nothing to do.")
        return 1

    print(f"Source: {describe(source_url)}")
    print(f"Target: {describe(target_url)}")

    source = sa.create_engine(source_url)
    target = sa.create_engine(target_url, pool_pre_ping=True)

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if current_revision(source) != head:
        print(f"Source database isn't fully migrated (at {current_revision(source)}, head is {head}). "
              "Run `python init_db.py` first.")
        return 1

    print("Running migrations on target...")
    config = alembic_config()
    with target.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    tables = Base.metadata.sorted_tables  # parents before children (FK order)

    with target.connect() as connection:
        non_empty = [t.name for t in tables if connection.execute(sa.select(sa.func.count()).select_from(t)).scalar()]
    if non_empty:
        print(f"Target already has data in: {', '.join(non_empty)}. Refusing to copy over it.")
        return 1

    counts = {}
    with source.connect() as src, target.begin() as dst:
        for table in tables:
            rows = [dict(row) for row in src.execute(sa.select(table)).mappings()]
            for start in range(0, len(rows), BATCH_SIZE):
                dst.execute(sa.insert(table), rows[start:start + BATCH_SIZE])
            counts[table.name] = len(rows)
            print(f"  {table.name:20} {len(rows):5} rows")

        if dst.dialect.name == "postgresql":
            # Rows were inserted with their original ids, which doesn't
            # advance Postgres' id sequences - without this, the next new
            # user/trade would try to reuse id 1 and fail.
            for table in tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, sa.Integer):
                    dst.execute(sa.text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 1), "
                        f"(SELECT MAX({pk[0].name}) FROM {table.name}) IS NOT NULL)"
                    ))

    with target.connect() as connection:
        mismatched = [
            t.name for t in tables
            if connection.execute(sa.select(sa.func.count()).select_from(t)).scalar() != counts[t.name]
        ]
    if mismatched:
        print(f"Row counts differ after copying: {', '.join(mismatched)}")
        return 1

    print(f"Done - copied {sum(counts.values())} rows across {len(tables)} tables, all counts match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
