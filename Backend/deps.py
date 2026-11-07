# Shared FastAPI dependencies, used by main.py and by route modules like
# brokerage.py. Living in their own module (instead of main.py) lets other
# route files import them without a circular import back into main.
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth import decode_access_token
from database import SessionLocal
from models import User

# Registers a proper "bearer token" security scheme with FastAPI, so
# Swagger UI's Authorize button can attach the token to every protected
# endpoint automatically.
bearer_scheme = HTTPBearer()


# Creates a fresh database connection for each request, and closes it
# automatically when the request finishes - prevents connections from
# piling up unused.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# AUTH: Dependency for protected endpoints - decodes the token via FastAPI's
# HTTPBearer security scheme, looks up the matching user, and returns it.
# Raises 401 if the token is missing, invalid, or the user no longer exists.
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials  # HTTPBearer already strips the "Bearer " prefix for us

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
