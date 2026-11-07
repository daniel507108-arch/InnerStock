# Routes for the linked-brokerage (SnapTrade / Wealthsimple) feature. The
# sync logic itself lives in snaptrade_sync.py; this file is just the HTTP
# layer: who may call what, and turning failures into clean responses.
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import snaptrade_sync
from deps import get_current_user, get_db
from models import BrokerageAccount, User

router = APIRouter(prefix="/brokerage", tags=["brokerage"])


def require_brokerage_access(current_user: User = Depends(get_current_user)) -> User:
    # The SnapTrade key is a PERSONAL key - it reads one specific person's
    # brokerage accounts. Only that person (SNAPTRADE_OWNER_EMAIL) may use
    # it; everyone else gets a 403 rather than someone else's trades.
    if not snaptrade_sync.is_available_for(current_user):
        raise HTTPException(status_code=403, detail="Brokerage sync isn't set up for this account")
    return current_user


# Always answers (never 403) so the frontend can decide whether to show
# the brokerage card at all.
@router.get("/status")
def get_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not snaptrade_sync.is_available_for(current_user):
        return {"available": False}
    return {"available": True, **snaptrade_sync.status(db, current_user)}


# Returns a one-time SnapTrade Connection Portal link (valid 5 minutes) for
# linking a new brokerage account or reconnecting an expired one.
@router.post("/connect")
def connect(current_user: User = Depends(require_brokerage_access)):
    try:
        return {"redirect_uri": snaptrade_sync.connection_portal_url(snaptrade_sync.get_client())}
    except snaptrade_sync.BrokerageError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Pulls new trades from every sync-enabled account. The dashboard calls
# this on load; calls within MIN_SYNC_INTERVAL of the last sync return the
# current status without hitting SnapTrade, unless force=true ("Sync now").
@router.post("/sync")
def sync(force: bool = False, db: Session = Depends(get_db), current_user: User = Depends(require_brokerage_access)):
    try:
        return snaptrade_sync.sync(db, current_user, force=force)
    except snaptrade_sync.BrokerageError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(e))


class AccountUpdate(BaseModel):
    sync_enabled: bool


# Turns syncing on/off for one linked account (e.g. leave crypto off).
@router.patch("/accounts/{account_id}")
def update_account(account_id: int, update: AccountUpdate, db: Session = Depends(get_db),
                   current_user: User = Depends(require_brokerage_access)):
    account = db.query(BrokerageAccount).filter(
        BrokerageAccount.id == account_id, BrokerageAccount.user_id == current_user.id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    account.sync_enabled = update.sync_enabled
    db.commit()
    return {"id": account.id, "sync_enabled": account.sync_enabled}
