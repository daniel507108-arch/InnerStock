import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# Local development defaults to the SQLite file in Backend/. A deployed
# environment sets DATABASE_URL (e.g. a hosted Postgres URL) instead.
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./innerstock.db"  # "or": an empty DATABASE_URL= line counts as unset


def normalize_database_url(url: str) -> str:
    # Hosts (Neon, Vercel, Render...) hand out "postgres://" or plain
    # "postgresql://" URLs. SQLAlchemy 2 rejects the first, and would use the
    # psycopg2 driver for the second - point both at psycopg 3, which is the
    # driver in requirements.txt.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalize_database_url(DATABASE_URL)

# check_same_thread is a SQLite-only option (FastAPI handles requests on
# multiple threads); other databases reject it.
IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

# pool_pre_ping: hosted Postgres (e.g. Neon) closes idle connections and
# suspends when unused, so check a pooled connection is still alive before
# handing it to a request instead of failing that request.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=not IS_SQLITE)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
