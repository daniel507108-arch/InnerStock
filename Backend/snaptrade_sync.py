# SnapTrade (Wealthsimple) sync: pulls trades from a linked brokerage into
# the trades table, so holdings stay current without anyone typing trades in.
#
# Two SnapTrade data sources are combined, because each covers the other's gap:
#   - account ACTIVITIES: the authoritative trade history, but SnapTrade only
#     refreshes it about once a day - a trade made today isn't in it yet.
#   - recent ORDERS: real-time, but only the last 24 hours.
# Today's trades come in from orders immediately; when the matching activity
# shows up the next day, it takes over that same row (see _apply) instead of
# creating a duplicate - so any thesis written in between stays attached.
#
# Using a PERSONAL SnapTrade key: the key itself is tied to one person's
# brokerage logins, so only the InnerStock user named in SNAPTRADE_OWNER_EMAIL
# may use it. Without that check, any logged-in user could pull the key
# owner's trades into their own account.
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import yfinance as yf
from sqlalchemy.orm import Session
from snaptrade_client import SnapTrade, SnapTradeAuth

from models import BrokerageAccount, Trade, User

# Trade dates/times are stored in US/Eastern market time - the same clock
# the rest of the app assumes (see Trade.trade_time), and the one both US
# and TSX tickers trade on. SnapTrade timestamps are UTC, so an evening trade
# would otherwise land on the wrong calendar day.
MARKET_TZ = ZoneInfo("America/New_York")

# Account types (SnapTrade's raw_type) that sync by default when an account
# is first seen. Crypto is off because yfinance can't price bare crypto
# symbols like "BTC"; cash-only accounts (MSB) have no trades to sync.
DEFAULT_SYNCED_ACCOUNT_TYPES = {"TFSA", "PERSONAL"}

# SnapTrade and yfinance spell some exchange suffixes differently. TSX
# Venture is ".VN" in SnapTrade but ".V" in yfinance - without this, every
# Venture holding would price at $0.
SNAPTRADE_TO_YFINANCE_SUFFIX = {".VN": ".V"}

# Quantities are fractional floats - two records count as "the same
# quantity" within this tolerance (same idea as main.SHARE_QTY_EPSILON).
QTY_MATCH_TOLERANCE = 1e-6

# Each incremental sync re-reads this many days before the last sync, in
# case SnapTrade backfilled an activity late. Re-reading is harmless: trades
# already imported are recognised by external_id and skipped.
RESYNC_OVERLAP_DAYS = 7

# Syncs closer together than this are skipped unless forced - the dashboard
# triggers a sync on load, and SnapTrade rate-limits personal keys per account.
MIN_SYNC_INTERVAL = timedelta(minutes=2)

ACTIVITY_PAGE_SIZE = 1000


class BrokerageError(Exception):
    """A SnapTrade call failed - surfaced to the user as a 502."""


# --- Configuration -------------------------------------------------------------

def is_configured() -> bool:
    return bool(os.getenv("SNAPTRADE_CLIENT_ID") and os.getenv("SNAPTRADE_CONSUMER_KEY"))


def is_owner(user: User) -> bool:
    owner = (os.getenv("SNAPTRADE_OWNER_EMAIL") or "").strip().lower()
    return bool(owner) and user.email.strip().lower() == owner


def is_available_for(user: User) -> bool:
    return is_configured() and is_owner(user)


def get_client() -> SnapTrade:
    return SnapTrade(auth=SnapTradeAuth.personal_api_key(
        consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY"),
        client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
    ))


def connection_portal_url(client: SnapTrade) -> str:
    """One-time link to SnapTrade's Connection Portal (expires in 5 minutes).

    The user logs in to their brokerage on SnapTrade's own page - InnerStock
    never sees brokerage credentials. "read" = read-only access, no trading.
    """
    try:
        return _body(client.authentication.login_snap_trade_user(connection_type="read"))["redirectURI"]
    except Exception as e:
        raise BrokerageError(f"Could not start a SnapTrade connection: {e}") from e


# --- Normalising SnapTrade records ----------------------------------------------

@dataclass
class BrokerTrade:
    """One buy/sell from SnapTrade, already in InnerStock's terms."""
    external_id: str          # "activity:<id>" or "order:<id>"
    ticker: str               # yfinance spelling
    action: str               # "buy" / "sell"
    quantity: float           # always positive
    price: float              # per share, in price_currency
    trade_date: date          # US/Eastern
    trade_time: time          # US/Eastern
    price_currency: str       # currency the price is quoted in
    security_currency: str    # currency the security itself trades in

    @property
    def is_order(self) -> bool:
        return self.external_id.startswith("order:")


def to_yfinance_ticker(symbol: str) -> str:
    ticker = symbol.strip().upper()
    for snaptrade_suffix, yfinance_suffix in SNAPTRADE_TO_YFINANCE_SUFFIX.items():
        if ticker.endswith(snaptrade_suffix):
            return ticker[: -len(snaptrade_suffix)] + yfinance_suffix
    return ticker


def root_symbol(ticker: str) -> str:
    """'ZIGY.V' -> 'ZIGY'. Used for matching against old CSV rows, which
    sometimes guessed the wrong exchange suffix (the CSV import labelled
    every CAD-priced symbol '.TO', including TSX Venture ones)."""
    return ticker.upper().split(".")[0]


def to_market_datetime(timestamp: str) -> tuple[date, time]:
    utc = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    local = utc.astimezone(MARKET_TZ)
    return local.date(), local.time().replace(microsecond=0)


def _number(value) -> float:
    return float(str(value)) if value is not None else 0.0


def _currency_code(value) -> str | None:
    return (value or {}).get("code") if value else None


def parse_activity(activity) -> BrokerTrade | None:
    """Account activity -> BrokerTrade, or None if it isn't a stock/ETF trade."""
    if activity.get("type") not in ("BUY", "SELL") or activity.get("option_symbol"):
        return None
    symbol = activity.get("symbol") or {}
    if not symbol.get("symbol"):
        return None

    quantity = abs(_number(activity.get("units")))  # sells come through negative
    price = _number(activity.get("price"))
    if quantity <= 0 or price <= 0 or not activity.get("trade_date"):
        return None

    trade_date, trade_time = to_market_datetime(activity["trade_date"])
    security_currency = _currency_code(symbol.get("currency"))
    return BrokerTrade(
        external_id=f"activity:{activity['id']}",
        ticker=to_yfinance_ticker(symbol["symbol"]),
        action=activity["type"].lower(),
        quantity=quantity,
        price=price,
        trade_date=trade_date,
        trade_time=trade_time,
        price_currency=_currency_code(activity.get("currency")) or security_currency or "CAD",
        security_currency=security_currency or "CAD",
    )


def parse_order(order) -> BrokerTrade | None:
    """Executed order -> BrokerTrade, or None if it isn't a filled stock/ETF trade."""
    if str(order.get("status") or "").upper() != "EXECUTED" or order.get("option_symbol"):
        return None
    action = str(order.get("action") or "").upper()
    symbol = order.get("universal_symbol") or {}
    if action not in ("BUY", "SELL") or not symbol.get("symbol"):
        return None

    quantity = abs(_number(order.get("filled_quantity")))
    price = _number(order.get("execution_price"))
    executed_at = order.get("time_executed") or order.get("time_updated")
    if quantity <= 0 or price <= 0 or not executed_at:
        return None

    trade_date, trade_time = to_market_datetime(executed_at)
    security_currency = _currency_code(symbol.get("currency")) or "CAD"
    return BrokerTrade(
        external_id=f"order:{order['brokerage_order_id']}",
        ticker=to_yfinance_ticker(symbol["symbol"]),
        action=action.lower(),
        quantity=quantity,
        price=price,
        trade_date=trade_date,
        trade_time=trade_time,
        price_currency=_currency_code(order.get("quote_currency")) or security_currency,
        security_currency=security_currency,
    )


# --- Currency ------------------------------------------------------------------

def usd_cad_rates(dates: set[date]) -> dict[date, float]:
    """CAD per 1 USD on each date (last close on or before it), from yfinance.

    Needed because Wealthsimple reports US-stock trades with the price
    already converted to CAD, while yfinance (and so the whole holdings
    calculation) prices US stocks in USD. Storing the CAD price would show
    a fake ~30% loss on every US position. Wealthsimple's own rate includes
    an FX fee (~1.5%), so the converted cost is close but not exact.
    """
    if not dates:
        return {}
    history = yf.Ticker("CAD=X").history(start=min(dates) - timedelta(days=7), end=max(dates) + timedelta(days=1))
    closes = sorted((ts.date(), float(close)) for ts, close in history["Close"].items())
    rates = {}
    for d in dates:
        earlier = [close for close_date, close in closes if close_date <= d]
        if earlier:
            rates[d] = earlier[-1]
    return rates


def _needs_usd_conversion(trade: BrokerTrade) -> bool:
    return trade.security_currency == "USD" and trade.price_currency == "CAD"


# --- Sync ------------------------------------------------------------------------

def _body(response):
    return response.body if hasattr(response, "body") else response


def sync_accounts(db: Session, user: User, client: SnapTrade) -> list[BrokerageAccount]:
    """Upserts the user's linked brokerage accounts from SnapTrade."""
    try:
        results = _body(client.account_information.list_all_user_accounts())["results"]
    except Exception as e:
        raise BrokerageError(f"Could not load accounts from SnapTrade: {e}") from e

    existing = {a.external_account_id: a for a in db.query(BrokerageAccount).filter(BrokerageAccount.user_id == user.id)}
    accounts = []
    for result in results:
        if result.get("kind") not in (None, "investment"):
            continue  # deposit/credit accounts have no trades
        account = existing.get(result["id"])
        raw_type = str(result.get("raw_type") or "").upper()
        if account is None:
            account = BrokerageAccount(
                user_id=user.id,
                external_account_id=result["id"],
                sync_enabled=raw_type in DEFAULT_SYNCED_ACCOUNT_TYPES,
            )
            db.add(account)
        account.name = result.get("display_name")
        account.account_type = raw_type.lower() or None
        account.institution = (account.name or "").replace(f" {raw_type}", "") or None
        accounts.append(account)
    db.flush()
    return accounts


def _fetch_activities(client: SnapTrade, account_id: str, start_date: date | None) -> list:
    activities, offset = [], 0
    while True:
        params = {"account_id": account_id, "type": "BUY,SELL", "offset": offset, "limit": ACTIVITY_PAGE_SIZE}
        if start_date:
            params["start_date"] = start_date
        body = _body(client.account_information.get_account_activities(**params))
        page = body.get("data", []) if hasattr(body, "get") else list(body)
        activities.extend(page)
        if len(page) < ACTIVITY_PAGE_SIZE:
            return activities
        offset += ACTIVITY_PAGE_SIZE


def _fetch_recent_orders(client: SnapTrade, account_id: str) -> list:
    body = _body(client.account_information.get_user_account_recent_orders(account_id=account_id, only_executed=True))
    return list(body.get("orders", []) if hasattr(body, "get") else body)


def _find_match(db: Session, user: User, trade: BrokerTrade, adoptable: bool) -> Trade | None:
    """An existing trade that is this same real-world trade.

    adoptable=True: only rows the broker record may take over - manual and
    old CSV trades (no external_id yet) and order-sourced rows (which the
    authoritative activity replaces).
    adoptable=False: rows already backed by an activity.
    """
    candidates = (
        db.query(Trade)
        .filter(Trade.user_id == user.id, Trade.action == trade.action, Trade.trade_date == trade.trade_date)
        .order_by(Trade.id)
        .all()
    )
    for candidate in candidates:
        external = candidate.external_id or ""
        if adoptable != (external == "" or external.startswith("order:")):
            continue
        if root_symbol(candidate.ticker) != root_symbol(trade.ticker):
            continue
        if abs(float(candidate.quantity) - trade.quantity) <= QTY_MATCH_TOLERANCE:
            return candidate
    return None


def _apply(db: Session, user: User, account: BrokerageAccount, trade: BrokerTrade, summary: dict):
    if db.query(Trade).filter(Trade.user_id == user.id, Trade.external_id == trade.external_id).first():
        summary["already_synced"] += 1
        return

    match = _find_match(db, user, trade, adoptable=True)
    if match is not None:
        if trade.is_order and (match.external_id or "").startswith("order:"):
            summary["already_synced"] += 1  # same order seen under another id
            return
        # Take over the existing row: it keeps its thesis, conviction and
        # grade; the broker record supplies the id, account, correct ticker
        # spelling and exact time. The existing price is kept for CSV rows
        # (converted with Wealthsimple's exact FX rate) and order rows (the
        # real execution price); a hand-entered manual price is replaced.
        if match.source == "manual":
            match.price_per_share = trade.price
        match.external_id = trade.external_id
        match.source = "snaptrade"
        match.brokerage_account_id = account.id
        match.ticker = trade.ticker
        match.trade_time = trade.trade_time
        summary["matched_existing"] += 1
        db.flush()
        return

    if trade.is_order and _find_match(db, user, trade, adoptable=False) is not None:
        summary["already_synced"] += 1  # the activity for this order is already in
        return

    db.add(Trade(
        user_id=user.id,
        ticker=trade.ticker,
        action=trade.action,
        quantity=trade.quantity,
        price_per_share=trade.price,
        trade_date=trade.trade_date,
        trade_time=trade.trade_time,
        source="snaptrade",
        external_id=trade.external_id,
        brokerage_account_id=account.id,
        # thesis/conviction/review_date stay empty - synced trades land in
        # /trades/incomplete for the user to write a thesis for.
    ))
    summary["new_trades"] += 1
    db.flush()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored naive UTC, like the rest of the app


def sync(db: Session, user: User, client: SnapTrade | None = None, force: bool = False) -> dict:
    """Pulls new trades for every sync-enabled account. Safe to run repeatedly."""
    stored = db.query(BrokerageAccount).filter(BrokerageAccount.user_id == user.id, BrokerageAccount.sync_enabled.is_(True)).all()
    if not force and stored and all(a.last_synced_at and _utcnow() - a.last_synced_at < MIN_SYNC_INTERVAL for a in stored):
        return {"skipped_recent_sync": True, **status(db, user)}

    client = client or get_client()
    accounts = [a for a in sync_accounts(db, user, client) if a.sync_enabled]

    summary = {"skipped_recent_sync": False, "accounts": [a.name for a in accounts],
               "new_trades": 0, "matched_existing": 0, "already_synced": 0, "skipped": [], "errors": []}

    # Activities before orders: when both describe the same trade, the
    # authoritative activity should claim the row first.
    pending = []
    for account in accounts:
        start = account.last_synced_at.date() - timedelta(days=RESYNC_OVERLAP_DAYS) if account.last_synced_at else None
        try:
            activities = _fetch_activities(client, account.external_account_id, start)
            orders = _fetch_recent_orders(client, account.external_account_id)
        except Exception as e:
            raise BrokerageError(f"Could not load trades for {account.name}: {e}") from e
        for record, parse in [(a, parse_activity) for a in activities] + [(o, parse_order) for o in orders]:
            trade = parse(record)
            if trade is None:
                summary["skipped"].append(_describe_skipped(record))
            else:
                pending.append((account, trade))

    fx_dates = {t.trade_date for _, t in pending if _needs_usd_conversion(t)}
    rates = usd_cad_rates(fx_dates) if fx_dates else {}

    for account, trade in pending:
        if _needs_usd_conversion(trade):
            rate = rates.get(trade.trade_date)
            if not rate:
                summary["errors"].append(f"No USD/CAD rate for {trade.ticker} on {trade.trade_date} - not imported yet, will retry next sync")
                continue
            trade.price = trade.price / rate
            trade.price_currency = "USD"
        _apply(db, user, account, trade, summary)

    synced_at = _utcnow()
    for account in accounts:
        account.last_synced_at = synced_at
    db.commit()

    summary.update(status(db, user))
    return summary


def _describe_skipped(record) -> str:
    symbol = (record.get("symbol") or record.get("universal_symbol") or {})
    name = symbol.get("symbol") if hasattr(symbol, "get") else None
    kind = record.get("type") or record.get("action") or "record"
    return f"{kind} {name or record.get('option_symbol') or ''}".strip()


def status(db: Session, user: User) -> dict:
    accounts = db.query(BrokerageAccount).filter(BrokerageAccount.user_id == user.id).order_by(BrokerageAccount.id).all()
    synced = [a.last_synced_at for a in accounts if a.sync_enabled and a.last_synced_at]
    return {
        "connected": bool(accounts),
        "last_synced_at": max(synced).isoformat() + "Z" if synced else None,
        "accounts_detail": [
            {"id": a.id, "name": a.name, "account_type": a.account_type, "sync_enabled": a.sync_enabled,
             "last_synced_at": a.last_synced_at.isoformat() + "Z" if a.last_synced_at else None}
            for a in accounts
        ],
        # Old CSV imports no broker record has claimed - trades SnapTrade
        # doesn't know about (or that differ from what it reports).
        "unmatched_csv_trades": db.query(Trade).filter(
            Trade.user_id == user.id, Trade.source == "csv", Trade.external_id.is_(None)
        ).count(),
    }
