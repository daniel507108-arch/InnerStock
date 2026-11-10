# Brings the database schema up to date by running every pending Alembic
# migration (same as running `alembic upgrade head` from Backend/).
#
# Safe to run any time, on a brand-new database or an existing one - it
# only applies migrations that haven't been applied yet. Schema changes
# are made by adding a migration in migrations/versions/, never by editing
# tables by hand or deleting innerstock.db.
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parent


def upgrade_to_latest():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_to_latest()
    print("Database ready: all migrations applied.")
