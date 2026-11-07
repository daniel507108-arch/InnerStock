import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# Local development defaults to the SQLite file in Backend/. A deployed
# environment sets DATABASE_URL (e.g. a hosted Postgres URL) instead.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./innerstock.db")

# Some hosts hand out "postgres://" URLs, which SQLAlchemy 2 no longer accepts.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# check_same_thread is a SQLite-only option (FastAPI handles requests on
# multiple threads); other databases reject it.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
