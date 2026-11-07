# Entry point for Vercel's Python runtime, which looks for a FastAPI `app`
# in a file named index.py / app.py / server.py. Locally keep using
# `uvicorn main:app --reload`; this file just re-exports that same app.
from main import app  # noqa: F401
