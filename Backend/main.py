# Import the main FastAPI class - this is the toolkit that lets us build a web server
from fastapi import FastAPI, Depends, HTTPException

# Import CORS middleware - this handles the "permission" between frontend and backend
from fastapi.middleware.cors import CORSMiddleware

# Import yfinance - lets us pull real stock data from Yahoo Finance
import yfinance as yf

# Import tools to talk to the database
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Trade

# Pydantic - lets us define exactly what shape incoming data must be,
# so FastAPI can validate it automatically before our code even runs
from pydantic import BaseModel
from datetime import date
from models import Trade, PriceCache, User, UserProfile, ChatMessage, SentimentCache, Watchlist
from datetime import date, datetime, timedelta, time

#FOR THE CLAUDE API
from dotenv import load_dotenv
import os
import anthropic


# AUTH: registers a proper "bearer token" security scheme with FastAPI, so
# Swagger UI's Authorize button recognizes it and can attach the token
# automatically to every protected endpoint - instead of needing a raw
# header typed in manually on each one.
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Per-million-token pricing for claude-sonnet-4-6, the model used for
# sentiment/bull-bear calls - used to turn a response's token usage into an
# actual dollar figure instead of leaving spend invisible. Update these if
# the model or its pricing changes.
CLAUDE_SONNET_4_6_INPUT_COST_PER_MTOK = 3.00
CLAUDE_SONNET_4_6_OUTPUT_COST_PER_MTOK = 15.00

from auth import hash_password, verify_password, create_access_token, decode_access_token
from typing import List, Optional

# For the AI rate limiter below. monotonic() is imported by name because
# `time` is already taken by datetime's time class above.
import threading
from collections import defaultdict, deque
from time import monotonic

# Create the actual app instance. Everything below attaches to this "app" object.
app = FastAPI()

# CORS setup: by default, browsers block a webpage on one address (localhost:5173)
# from fetching data from a different address (localhost:8000) unless the second
# one explicitly allows it. This block gives that permission.
# Deployed frontends (e.g. the Vercel URL) are added through the
# ALLOWED_ORIGINS env var as a comma-separated list - local dev works
# without setting anything.
ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:5174"] + [
    origin.strip().rstrip("/") for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # only allow requests from our React app's address(es)
    allow_methods=["*"],                       # allow all request types (GET, POST, etc.)
    allow_headers=["*"],                       # allow all header types
)

# get_db / get_current_user live in deps.py so other route modules (e.g.
# brokerage.py) can share them without importing main.
from deps import bearer_scheme, get_db, get_current_user

# Linked-brokerage (SnapTrade / Wealthsimple) routes: /brokerage/*
from brokerage import router as brokerage_router
app.include_router(brokerage_router)

# "Why did you make this trade?" inbox + reasons summary: /trades/needs-thesis,
# /trades/thesis, /trades/reasons, /trades/reasons-summary
import thesis
app.include_router(thesis.router)

# AI RATE LIMITING: every endpoint that can trigger a real Claude call
# (sentiment, bull/bear, advisor chat) costs money per hit, so each user
# gets a capped number of Claude calls per rolling window. Without this, a
# logged-in user (or a script using their token) could loop over tickers
# or spam the chat and run up the API bill with no ceiling.
#
# Buckets are separate so heavy dashboard use (one sentiment lookup per
# holding) can't lock someone out of the advisor chat, and vice versa.
# Values are (max_calls, window_seconds) - tune here if real usage needs it.
#
# Kept in memory on purpose: no new dependency or DB table needed. The
# trade-off is that counts reset when the server restarts and aren't shared
# across multiple worker processes - fine for a single uvicorn process, but
# this would need to move to Redis or the DB once there are several workers.
AI_RATE_LIMITS = {
    "analysis": (60, 3600),  # /sentiment + /bullbear, Claude calls only (cache hits are free)
    "chat": (40, 3600),      # /chat messages
}
_ai_call_log = defaultdict(deque)  # (user_id, bucket) -> timestamps of recent calls
_ai_call_lock = threading.Lock()   # sync routes run in a threadpool, so guard the shared dict


def enforce_ai_rate_limit(user_id: int, bucket: str):
    max_calls, window_seconds = AI_RATE_LIMITS[bucket]
    now = monotonic()

    with _ai_call_lock:
        calls = _ai_call_log[(user_id, bucket)]

        # Drop timestamps that have aged out of the rolling window
        while calls and now - calls[0] >= window_seconds:
            calls.popleft()

        if len(calls) >= max_calls:
            # The oldest call in the window is the next one to expire, so
            # that's how long until a slot frees up.
            retry_after = int(window_seconds - (now - calls[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"AI request limit reached. Try again in about {max(1, retry_after // 60)} minute(s).",
                headers={"Retry-After": str(retry_after)},
            )

        calls.append(now)

# This defines exactly what fields a new trade submission must contain, taken from Pydantic
# If someone sends data missing a required field or with the wrong type,
# FastAPI automatically rejects it with a clear error - before our code runs.
class TradeCreate(BaseModel):
    ticker: str
    action: str
    quantity: float
    price_per_share: float
    trade_date: date
    trade_time: time  # NEW - required, powers the intraday price auto-fill
    thesis_text: str
    conviction_score: int
    review_date: date
    # Why the trade was made, from thesis.BUY_REASONS / SELL_REASONS.
    # Optional at the API level so older clients keep working; the Log
    # Trade form asks for at least one.
    reason_tags: List[str] = []

from pydantic import BaseModel, EmailStr

class WatchlistAdd(BaseModel):
    ticker: str

class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileSubmit(BaseModel):
    risk_tolerance: str
    investing_goals: str
    trading_style: List[str]  # multi-select, comma-joined for storage - same pattern as sectors_of_interest below
    time_horizon: str
    income_bracket: str
    experience_level: str
    sectors_of_interest: List[str]
    biggest_fear: Optional[str] = None  # truly optional - None is fine, empty string is fine

# This is a "route" - it defines what happens when someone visits a specific URL.
# @app.get("/") means: when someone visits the homepage using a GET request, run this function.
@app.get("/")
def root():
    # FastAPI automatically converts this Python dictionary into JSON for us.
    return {"message": "InnerStock backend is running"}

# How long a cached price is considered "fresh enough" before we re-hit
# yfinance for it. This used to be 15 minutes, which - stacked with the
# frontend only fetching /holdings on page load/mount - meant a price on
# screen could visibly lag the real market by 15+ minutes even on a page
# the user was actively looking at. Note this is a ceiling, not a
# guarantee: yfinance's own free data is itself typically delayed
# (commonly ~15-20 min behind the live tape), so dropping this further
# tightens how often we re-check yfinance, but doesn't make the
# underlying data source real-time. Paired with the frontend's polling
# interval (see Dashboard.jsx / SidebarWatchlist.jsx) so a poll actually
# has a chance of landing on a fresh fetch instead of just re-reading the
# same stale cache row.
PRICE_CACHE_TTL_SECONDS = 45

# Shared logic: returns cached price data if fresh, otherwise fetches from
# yfinance, saves it to the cache, and returns it. Used by both /stock/{ticker}
# and /holdings, so a holding never shows $0 just because nobody visited
# /stock/{ticker} for it first.
def get_or_fetch_price(ticker: str, db: Session):
    ticker = ticker.upper()

    cached = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()

    if cached and cached.last_updated:
        age = datetime.utcnow() - cached.last_updated
        if age < timedelta(seconds=PRICE_CACHE_TTL_SECONDS):
            return cached  # fresh enough, return as-is

    # No cache, or it's stale - fetch fresh data
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        # Fetch failed - log the actual error so it's visible in the terminal,
        # instead of silently showing up as an unexplained $0 later.
        print(f"yfinance fetch failed for {ticker}: {e}")
        # Fall back to whatever old cached data exists (may be None)
        # rather than crashing the whole request
        return cached

    # yfinance only populates "currentPrice" for equities (quoteType
    # "EQUITY") - ETFs like VFV.TO/XEQT.TO come back with currentPrice=None
    # and the live price sitting in "regularMarketPrice" instead. Without
    # this fallback every ETF holding silently priced at $0.
    price = info.get("currentPrice")
    if price is None:
        price = info.get("regularMarketPrice")
    if price is None:
        return cached  # invalid ticker or no data - same fallback

    previous_close = info.get("previousClose")
    market_cap = info.get("marketCap")
    pe_ratio = info.get("trailingPE")
    sector = info.get("sector")
    # NEW - fundamentals for the advisor chat. Same info dict already
    # fetched above, just reading more keys out of it - no extra API call.
    forward_pe = info.get("forwardPE")
    price_to_book = info.get("priceToBook")
    profit_margins = info.get("profitMargins")
    revenue_growth = info.get("revenueGrowth")
    debt_to_equity = info.get("debtToEquity")
    dividend_yield = info.get("dividendYield")

    if cached:
        cached.current_price = price
        cached.previous_close = previous_close
        cached.market_cap = market_cap
        cached.pe_ratio = pe_ratio
        cached.sector = sector
        cached.forward_pe = forward_pe
        cached.price_to_book = price_to_book
        cached.profit_margins = profit_margins
        cached.revenue_growth = revenue_growth
        cached.debt_to_equity = debt_to_equity
        cached.dividend_yield = dividend_yield
        cached.last_updated = datetime.utcnow()
    else:
        cached = PriceCache(
            ticker=ticker,
            current_price=price,
            previous_close=previous_close,
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            sector=sector,
            forward_pe=forward_pe,
            price_to_book=price_to_book,
            profit_margins=profit_margins,
            revenue_growth=revenue_growth,
            debt_to_equity=debt_to_equity,
            dividend_yield=dividend_yield,
            last_updated=datetime.utcnow()
        )
        db.add(cached)

    db.commit()
    db.refresh(cached)
    return cached

# --- /stock/{ticker} route ---
# Now just calls the shared helper above and formats the response.
# All the actual caching/fetching logic lives in get_or_fetch_price.
# NOT user-scoped - this is a public price lookup, not tied to any
# specific person's portfolio, so no login required here.
@app.get("/stock/{ticker}")
def get_stock(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper()
    cached = get_or_fetch_price(ticker, db) #Uses function above

    # If the helper couldn't get real data (invalid ticker, fetch failed,
    # and there was nothing cached to fall back on), return a clean error
    if not cached:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or has no price data")

    return {
        "ticker": cached.ticker,
        "price": float(cached.current_price),
        "market_cap": float(cached.market_cap) if cached.market_cap else None,
        "pe_ratio": float(cached.pe_ratio) if cached.pe_ratio else None,
        "sector": cached.sector,
        "source": "cache/yfinance"
    }

# Given a ticker and the date (and optionally time) a trade happened,
# returns the best price we can find for that exact moment - used by
# TradeForm to auto-fill price_per_share more accurately than "whatever
# the price is right now" once a trade_date is known.
#
# Yahoo only retains 1-minute intraday history for roughly the last 7
# days. Inside that window (and only when a trade_time was actually
# given) we fetch 1-minute bars - including pre/post-market, since a
# trade logged at e.g. 8pm is after the 4pm regular-hours close and
# would otherwise have no real bar anywhere near it - and return
# whichever bar is closest to the requested time - "intraday" precision.
# If the closest bar we can find is still more than INTRADAY_MATCH_TOLERANCE_MINUTES
# away (e.g. the request lands overnight, when nothing trades at all,
# even pre/post-market), that's not a real match - we fall through to
# the daily-close fallback below instead of mislabeling a distant bar as
# precise. Outside the 7-day window, or when no time was given at all,
# we go straight to that fallback - "daily-close" precision - and say so
# explicitly in the response, since it's a meaningfully less precise
# number and the frontend should tell the user that rather than passing
# it off as exact.
# NOT user-scoped - same as /stock/{ticker}, a public price lookup.
INTRADAY_MATCH_TOLERANCE_MINUTES = 30

@app.get("/stock/{ticker}/price-at")
def get_price_at(ticker: str, trade_date: date, trade_time: str = None):
    ticker = ticker.upper()
    stock = yf.Ticker(ticker)

    days_ago = (datetime.now().date() - trade_date).days
    intraday_available = 0 <= days_ago <= 7

    if intraday_available and trade_time:
        hist = None
        try:
            hour, minute = (int(part) for part in trade_time.split(":")[:2])
            requested_dt = datetime.combine(trade_date, time(hour, minute))
            hist = stock.history(
                start=trade_date,
                end=trade_date + timedelta(days=1),
                interval="1m",
                prepost=True,
            )
        except Exception as e:
            print(f"yfinance intraday history fetch failed for {ticker}: {e}")

        if hist is not None and not hist.empty:
            # hist.index is timezone-aware in the exchange's local time
            # (Eastern, for both US tickers and .TO/TSX ones) - strip
            # tzinfo so it compares against our naive requested_dt, which
            # we're treating as Eastern too (see models.py's trade_time
            # comment for why that assumption is safe here).
            hist_naive_index = hist.index.tz_localize(None)
            closest_pos = hist_naive_index.get_indexer([requested_dt], method="nearest")[0]
            matched_time = hist_naive_index[closest_pos]
            gap_minutes = abs((matched_time.to_pydatetime() - requested_dt).total_seconds()) / 60

            if gap_minutes <= INTRADAY_MATCH_TOLERANCE_MINUTES:
                price = float(hist["Close"].iloc[closest_pos])
                return {
                    "ticker": ticker,
                    "price": round(price, 4),
                    "precision": "intraday",
                    "matched_time": matched_time.strftime("%H:%M"),
                }
            # else: closest bar is too far from what was asked for (e.g.
            # requested time fell overnight) - fall through to daily-close.

    # Fallback: that day's closing price. If trade_date fell on a
    # weekend/holiday, history() just returns whatever trading days
    # actually exist in the range, so we look back a few extra days and
    # take the most recent bar - effectively "last close on or before
    # trade_date."
    try:
        hist = stock.history(
            start=trade_date - timedelta(days=5),
            end=trade_date + timedelta(days=1),
            interval="1d",
        )
    except Exception as e:
        print(f"yfinance daily history fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not fetch price history for '{ticker}'")

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No price data found for '{ticker}' around {trade_date}")

    price = float(hist["Close"].iloc[-1])
    return {
        "ticker": ticker,
        "price": round(price, 4),
        "precision": "daily-close",
        "note": "Exact intraday price isn't available this far back - using that day's closing price instead.",
    }

# Creates a new trade. Takes JSON matching the TradeCreate shape above,
# saves it to the database, and returns the saved trade (now with an id).
# PROTECTED + SCOPED: requires login, and the new trade is stamped with
# whoever's actually logged in - never trusted from the client, so no one
# can create a trade under someone else's account.
@app.post("/trades") # When front end sents POST request to /trades this will run
def create_trade(trade: TradeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): #Uses function get_db to open a connection to database
    reason_tags = thesis.validate_tags(trade.action, trade.reason_tags)
    new_trade = Trade( #CONSTRUCTOR
        user_id=current_user.id,  # taken from the logged-in user, not the client
        ticker=trade.ticker,
        action=trade.action,
        quantity=trade.quantity,
        price_per_share=trade.price_per_share,
        trade_date=trade.trade_date,
        trade_time=trade.trade_time,
        thesis_text=trade.thesis_text,
        conviction_score=trade.conviction_score,
        review_date=trade.review_date,
        reason_tags=",".join(reason_tags) or None,
        thesis_written_at=datetime.utcnow(),  # written at logging time, by definition
    )
    db.add(new_trade)      # stage the new trade for saving
    db.commit()             # actually save it to the database
    db.refresh(new_trade)   # reload it, so we get the auto-generated id back
    return new_trade

# Returns every trade currently saved in the database.
# PROTECTED + SCOPED: only returns trades belonging to whoever's logged in.
@app.get("/trades")
def get_trades(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Trade).filter(Trade.user_id == current_user.id).all()

# Puts all trades into current holdings, calculates each position's
# share of the total portfolio, and flags any position over 20%.
# PROTECTED + SCOPED: only aggregates the logged-in user's own trades.
# Share counts at or below this are treated as zero. Fractional shares are
# stored and summed as floats, and floats can't represent most decimals
# exactly - e.g. buying 0.1 + 0.2 shares then selling 0.3 leaves
# 0.0000000000000000555 shares "held", which used to show up as a ghost
# position with a nonsense avg_cost. Brokers only go to a handful of
# decimal places, so anything this small is rounding noise, not real shares.
SHARE_QTY_EPSILON = 1e-9

@app.get("/holdings")
def get_holdings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Ordered chronologically - cost_tracking below needs trades in the order
    # they actually happened, since a sell has to know the average cost built
    # up by the buys that came before it.
    trades = db.query(Trade).filter(Trade.user_id == current_user.id).order_by(Trade.trade_date, Trade.id).all()

    # Step 1: tally net shares held per ticker (buys add, sells subtract)
    holdings = {}
    # NEW: moving-average cost basis per ticker (same method brokerages use
    # for ACB). total_qty here tracks shares currently held (not "ever
    # bought") - a sell removes shares at the position's average cost, which
    # shrinks total_cost proportionally but leaves the average cost per
    # remaining share unchanged. Without this, a fully-exited lot (bought
    # and later completely sold) would still drag up the avg_cost of shares
    # bought afterwards, which don't actually share any cost history with it.
    cost_tracking = {}

    # NEW: a second, parallel ACB tracker containing ONLY today's buys, net
    # of any sells that happened today too. This is what lets day_gain_loss
    # below tell "shares I've held since before today" (correctly measured
    # from previous_close) apart from "shares I bought today" (which should
    # be measured from what I actually paid for them, not the previous
    # close - I never experienced the move from market open to my buy).
    # trade_date has no time component, so if a ticker is both bought AND
    # sold today, we can't know the real order - we assume the sell comes
    # out of today's newly-bought shares first. That's the conservative
    # read: it avoids crediting "today's gain" to shares that, by the time
    # you're looking at this, you may no longer even hold.
    today = date.today()
    today_tracking = {}

    for trade in trades:
        ticker = trade.ticker.upper()
        if ticker not in holdings:
            holdings[ticker] = 0
        if ticker not in cost_tracking:
            cost_tracking[ticker] = {"total_cost": 0, "total_qty": 0}
        if ticker not in today_tracking:
            today_tracking[ticker] = {"total_cost": 0, "total_qty": 0}

        qty = float(trade.quantity)
        price = float(trade.price_per_share)
        is_today = trade.trade_date == today

        if trade.action == "buy":
            holdings[ticker] += qty
            cost_tracking[ticker]["total_cost"] += qty * price
            cost_tracking[ticker]["total_qty"] += qty
            if is_today:
                today_tracking[ticker]["total_cost"] += qty * price
                today_tracking[ticker]["total_qty"] += qty
        elif trade.action == "sell":
            holdings[ticker] -= qty
            held_qty = cost_tracking[ticker]["total_qty"]
            if held_qty > 0:
                avg_cost_before_sell = cost_tracking[ticker]["total_cost"] / held_qty
                cost_tracking[ticker]["total_cost"] -= avg_cost_before_sell * qty
                cost_tracking[ticker]["total_qty"] -= qty
                # Fully exited (allowing for float rounding, see
                # SHARE_QTY_EPSILON) - reset to a clean zero so leftover
                # rounding noise can't leak into the cost of a later rebuy.
                if cost_tracking[ticker]["total_qty"] <= SHARE_QTY_EPSILON:
                    cost_tracking[ticker] = {"total_cost": 0, "total_qty": 0}
            # Sells reduce today's bucket first (see comment above) - capped
            # at whatever's actually in it, since a sell can also be selling
            # older shares that were never in today's bucket to begin with.
            today_qty = today_tracking[ticker]["total_qty"]
            if today_qty > 0:
                sell_from_today = min(qty, today_qty)
                avg_cost_today_before_sell = today_tracking[ticker]["total_cost"] / today_qty
                today_tracking[ticker]["total_cost"] -= avg_cost_today_before_sell * sell_from_today
                today_tracking[ticker]["total_qty"] -= sell_from_today

    # Step 2: drop any ticker fully sold out (0 or negative shares left,
    # allowing for float rounding - see SHARE_QTY_EPSILON)
    holdings = {ticker: shares for ticker, shares in holdings.items() if shares > SHARE_QTY_EPSILON}

    # Step 3: look up current price for each holding, calculate dollar value
    holdings_list = []
    total_value = 0

    for ticker, shares in holdings.items():
        cached = get_or_fetch_price(ticker, db)
        current_price = float(cached.current_price) if cached else 0

        # NEW: yesterday's closing price, used for "today's" gain/loss below.
        # Falls back to current_price if we don't have a previous_close yet
        # (e.g. right after adding this column, before every ticker's been
        # re-fetched) so the math doesn't crash or produce a huge fake number.
        previous_close = float(cached.previous_close) if cached and cached.previous_close else current_price

        value = shares * current_price
        total_value += value

        # NEW: moving-average cost of the shares currently held (see
        # cost_tracking comment above - sells already kept this in sync)
        held_qty = cost_tracking[ticker]["total_qty"]
        if held_qty > 0:
            avg_cost = cost_tracking[ticker]["total_cost"] / held_qty
        else:
            avg_cost = 0  # shouldn't normally happen, but guards against divide-by-zero

        # NEW: all-time gain/loss - compares current price to what you paid
        # on average, across the whole time you've held this position
        total_gain_loss = (current_price - avg_cost) * shares
        total_gain_loss_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

        # NEW: today's gain/loss - blended across two baselines instead of
        # one flat "vs previous_close" for the whole position. Shares held
        # since before today are measured from previous_close as before;
        # shares bought today are measured from what you actually paid for
        # them today (today_tracking, built above), since previous_close
        # includes price movement from market open to your buy that you
        # never actually experienced. For a position with no same-day buys
        # this reduces to exactly the old formula - see the math check in
        # the fix writeup for why. This is what lets the frontend toggle
        # between "today" and "all-time" views without needing a second API
        # call - both numbers are always here.
        shares_bought_today = today_tracking[ticker]["total_qty"]
        shares_from_before_today = shares - shares_bought_today
        avg_price_paid_today = (
            today_tracking[ticker]["total_cost"] / shares_bought_today
            if shares_bought_today > 0 else 0
        )

        day_gain_loss = (
            shares_from_before_today * (current_price - previous_close)
            + shares_bought_today * (current_price - avg_price_paid_today)
        )

        # Denominator is each bucket's own baseline value, not a single
        # previous_close - so day_gain_loss_percent reflects the blend too,
        # not just "how much did the stock move today" (which is all the
        # old formula could ever say, regardless of when you bought).
        day_baseline_value = (
            shares_from_before_today * previous_close
            + shares_bought_today * avg_price_paid_today
        )
        day_gain_loss_percent = (
            (day_gain_loss / day_baseline_value * 100) if day_baseline_value > 0 else 0
        )

        holdings_list.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": current_price,
            "avg_cost": round(avg_cost, 2),
            "value": value,
            "total_gain_loss": round(total_gain_loss, 2),
            "total_gain_loss_percent": round(total_gain_loss_percent, 2),
            "day_gain_loss": round(day_gain_loss, 2),
            "day_gain_loss_percent": round(day_gain_loss_percent, 2)
        })

    # Step 4: now that total_value is known, calculate each holding's % share
    for holding in holdings_list:
        if total_value > 0:
            percentage = (holding["value"] / total_value) * 100
        else:
            percentage = 0

        holding["percentage"] = round(percentage, 2)
        holding["overweight_flag"] = percentage > 20

    # NEW: average conviction score per holding, then averaged across positions.
    # Only buy trades carry conviction (that's when the thesis was written),
    # so a ticker bought multiple times at different conviction levels gets
    # averaged first per-ticker, so one heavily-DCA'd position doesn't skew
    # the portfolio number more than any other position.
    conviction_by_ticker = {}
    for trade in trades:
        ticker = trade.ticker.upper()
        if ticker in holdings and trade.action == "buy" and trade.conviction_score is not None:
            conviction_by_ticker.setdefault(ticker, []).append(trade.conviction_score)

    per_ticker_avg_conviction = [
        sum(scores) / len(scores) for scores in conviction_by_ticker.values()
    ]
    avg_conviction = (
        sum(per_ticker_avg_conviction) / len(per_ticker_avg_conviction)
        if per_ticker_avg_conviction else 0
    )
    # NEW: portfolio-wide today's gain/loss, derived from each holding's
    # day_gain_loss. Subtracting today's total gain from total_value gives
    # each holding's own day_baseline_value summed up - "yesterday's close"
    # for positions held since before today, but "what I paid today" for
    # anything bought today (which never had a "yesterday" in the
    # portfolio). Despite the variable name this isn't literally "the
    # portfolio's value as of yesterday's close" once same-day buys are
    # involved - it's the correct blended baseline for day_change_percent,
    # which is the only thing this number is used for.
    total_day_gain_loss = sum(h["day_gain_loss"] for h in holdings_list)
    portfolio_value_yesterday = total_value - total_day_gain_loss
    day_change_percent = (
        (total_day_gain_loss / portfolio_value_yesterday * 100)
        if portfolio_value_yesterday > 0 else 0
    )
    return {
        "holdings": holdings_list,
        "total_value": total_value,
        "position_count": len(holdings_list),
        "day_change_value": round(total_day_gain_loss, 2),
        "day_change_percent": round(day_change_percent, 2),
        "avg_conviction": round(avg_conviction, 2)
    }

# Uses Claude to generate a bull case, bear case, and key risk for a given
# ticker, based on data we already have cached (no new yfinance call needed).
# The analysis itself is stock-level (not tied to a specific portfolio), but
# the route is PROTECTED: every hit is a paid Claude call, so it requires
# login and counts against the user's "analysis" rate limit.
@app.get("/bullbear/{ticker}")
def get_bull_bear(ticker: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = ticker.upper()

    # Checked before the price lookup too, so a rate-limited user doesn't
    # trigger yfinance calls either. No cache on this route, so every
    # request is a Claude call and always counts.
    enforce_ai_rate_limit(current_user.id, "analysis")

    # Reuse the same helper /holdings uses - checks the cache first, and
    # automatically fetches fresh data from yfinance if it's missing or stale,
    # instead of just giving up when nothing's cached yet.
    cached = get_or_fetch_price(ticker, db)

    if not cached:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or has no price data")

    prompt = f"""Give a brief bull case, bear case, and key risk for {ticker} stock.
Current price: {cached.current_price}
Sector: {cached.sector}
P/E ratio: {cached.pe_ratio}
Market cap: {cached.market_cap}

Format your response as:
Bull Case: [1-2 sentences]
Bear Case: [1-2 sentences]
Key Risk: [1 sentence]"""

    try:
        message = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"Claude API call failed for {ticker} bull/bear: {e}")
        raise HTTPException(status_code=404, detail="Could not generate bull/bear analysis")

    return {
        "ticker": ticker,
        "analysis": message.content[0].text
    }

# Returns every trade where the review date has passed but it hasn't
# been graded yet (outcome_tag still null) - these are "due for review."
# PROTECTED + SCOPED: only the logged-in user's own trades are checked.
@app.get("/thesis-reviews")
def get_thesis_reviews(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    today = date.today()
    due_trades = db.query(Trade).filter(
        Trade.user_id == current_user.id,
        Trade.review_date <= today,
        Trade.outcome_tag.is_(None)
    ).all()

    reviews = []
    for trade in due_trades:
        fomo_result = check_fomo_for_trade(trade)  # NEW

        reviews.append({
            "id": trade.id,
            "ticker": trade.ticker,
            "action": trade.action,
            "thesis_text": trade.thesis_text,
            "conviction_score": trade.conviction_score,
            "trade_date": trade.trade_date.isoformat(),
            "review_date": trade.review_date.isoformat(),
            "fomo_flag": fomo_result["fomo_flag"],  # NEW
            "fomo_reason": fomo_result["reason"]  # NEW
        })

    return {"reviews": reviews}

# Returns trades that HAVE been graded (outcome_tag is set), most recent
# first, for the "Recently reviewed" section — the counterpart to
# /thesis-reviews above, which only returns trades still PENDING review.
# PROTECTED + SCOPED: only the logged-in user's own reviewed trades.
@app.get("/thesis-reviews/recent")
def get_recent_thesis_reviews(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reviewed_trades = (
        db.query(Trade)
        .filter(Trade.user_id == current_user.id, Trade.outcome_tag.isnot(None))
        .order_by(Trade.created_at.desc())
        .limit(10)
        .all()
    )

    reviews = [
        {
            "id": t.id,
            "ticker": t.ticker,
            "action": t.action,
            "thesis_text": t.thesis_text,
            "conviction_score": t.conviction_score,
            "outcome_tag": t.outcome_tag,
            "review_notes": t.review_notes,
        }
        for t in reviewed_trades
    ]
    return {"reviews": reviews}

# Defines what a valid outcome update must look like
class OutcomeUpdate(BaseModel):
    outcome_tag: str  # expected: "correct", "incorrect", or "mixed"
    review_notes: Optional[str] = None  # optional freeform reflection, saved alongside the grade


# Updates one specific trade's outcome_tag. Once set, that trade stops
# showing up in GET /thesis-reviews above.
# PROTECTED + SCOPED: confirms the trade actually belongs to the logged-in
# user before allowing the update - otherwise anyone could edit anyone
# else's trade just by guessing an id number.
@app.patch("/trades/{trade_id}/outcome") #PATCH HTTP method updates something existing
def update_trade_outcome(trade_id: int, update: OutcomeUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == current_user.id).first()

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade with id {trade_id} not found")

    trade.outcome_tag = update.outcome_tag
    trade.review_notes = update.review_notes
    db.commit()

    return {"success": True, "id": trade_id, "outcome_tag": trade.outcome_tag, "review_notes": trade.review_notes}

# Pulls recent news headlines via yfinance, sends them to Claude for a
# single overall sentiment classification, and returns exactly one of:
# "positive", "neutral", "negative".
# NOT user-scoped - stock-level sentiment, not tied to a specific portfolio.
# PROTECTED: a cache miss here means a paid Claude call, so the route
# requires login and cache misses count against the "analysis" rate limit.
@app.get("/sentiment/{ticker}")
def get_sentiment(ticker: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = ticker.upper()  # normalize, same habit as our other stock routes

    # Sentiment costs a real Claude API call to generate, unlike a price
    # lookup - and the frontend badge re-fetches every time the dashboard
    # mounts, which was calling Claude once per holding on every single
    # page visit. Cache it for an hour so repeat visits within the window are
    # free reads from the DB instead of new API calls.
    cached = db.query(SentimentCache).filter(SentimentCache.ticker == ticker).first()
    if cached and cached.last_updated and datetime.utcnow() - cached.last_updated < timedelta(minutes=60):
        # "unavailable" is a cached marker (see below) for ETFs that
        # structurally have no per-ticker news on yfinance - skip straight
        # to the same 404 the caller would get anyway, without re-hitting
        # yfinance for something that will never have news.
        if cached.sentiment == "unavailable":
            raise HTTPException(status_code=404, detail=f"No news available for ticker '{ticker}'")
        return {"ticker": ticker, "sentiment": cached.sentiment, "summary": cached.summary}

    # Only cache misses reach this point, so fresh cache reads above never
    # use up the user's limit - just the requests that lead to a new
    # Claude call.
    enforce_ai_rate_limit(current_user.id, "analysis")

    # Ask yfinance for recent news articles about this ticker.
    # stock.news is a DIFFERENT dataset than stock.info - this one returns
    # a list of news article dictionaries, not price/fundamentals data.
    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news
    except Exception as e:
        print(f"yfinance news fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not fetch news for ticker '{ticker}'")

    # CAD-hedged CDR tickers (e.g. GOOG.TO, AAPL.TO) already carry the real
    # company's news directly on yfinance - no fallback needed. Genuine TSX
    # ETFs (VFV.TO, XEQT.TO, MUU.TO) never have their own news coverage, and
    # stripping ".TO" to guess a US equivalent is NOT safe for these: e.g.
    # bare "MUU" resolves to an unrelated Direxion leveraged ETF, not the
    # user's actual SavvyLong holding. Distinguish the two with yfinance's
    # own quoteType instead of guessing from the ticker string: ETFs get a
    # permanent "unavailable" cache entry (they'll never have news), while
    # non-ETF ".TO" tickers with no news (a real CDR yfinance hasn't mapped)
    # fall back to the bare ticker, which is safe for equities/CDRs.
    if not news_items and ticker.endswith(".TO"):
        quote_type = None
        try:
            quote_type = stock.info.get("quoteType")
        except Exception as e:
            print(f"yfinance quoteType lookup failed for {ticker}: {e}")

        if quote_type == "ETF":
            if cached:
                cached.sentiment = "unavailable"
                cached.summary = "No news available for this ETF."
                cached.last_updated = datetime.utcnow()
            else:
                cached = SentimentCache(ticker=ticker, sentiment="unavailable", summary="No news available for this ETF.")
                db.add(cached)
            db.commit()
            raise HTTPException(status_code=404, detail=f"No news available for ticker '{ticker}'")
        else:
            base_ticker = ticker[:-3]  # strip ".TO"
            try:
                news_items = yf.Ticker(base_ticker).news
            except Exception as e:
                print(f"yfinance fallback news fetch failed for {base_ticker}: {e}")

    if not news_items:
        raise HTTPException(status_code=404, detail=f"No news available for ticker '{ticker}'")

    headlines = []
    for item in news_items[:5]: #First 5 headlines
        title = item.get("content", {}).get("title") or item.get("title")
        if title:
            headlines.append(title)

    if not headlines:
        raise HTTPException(status_code=404, detail=f"No usable headlines found for ticker '{ticker}'")

    prompt = f"""Here are recent headlines about {ticker} stock:

    # End result: a clean bulleted list of headlines, like:
    #   - Apple announces new AI chip
    #   - iPhone sales beat expectations
{chr(10).join(f"- {h}" for h in headlines)}

Respond in exactly this two-line format, nothing else:
SENTIMENT: [positive/neutral/negative]
SUMMARY: [two sentences explaining why, based on the headlines]"""

    # max_tokens bumped up from 10 to 150 - we now need room for a full
    # two-sentence summary, not just a single word
    try:
        message = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = message.content[0].text.strip()

        # message.usage carries the actual input/output token counts for
        # THIS call - multiply by the per-token price to get real dollars
        # spent, and print it so cost is visible in the uvicorn console
        # without needing to store or return it anywhere.
        cost_usd = (
            message.usage.input_tokens / 1_000_000 * CLAUDE_SONNET_4_6_INPUT_COST_PER_MTOK
            + message.usage.output_tokens / 1_000_000 * CLAUDE_SONNET_4_6_OUTPUT_COST_PER_MTOK
        )
        print(f"[sentiment] {ticker}: ${cost_usd:.6f} ({message.usage.input_tokens} in / {message.usage.output_tokens} out tokens)")
    except Exception as e:
        print(f"Claude API call failed for {ticker} sentiment: {e}")
        raise HTTPException(status_code=404, detail="Could not generate sentiment analysis")

    # Set defaults first, in case parsing below doesn't find one or both labels
    sentiment = "neutral"
    summary = "No summary available."

    # Split Claude's reply into individual lines and look for our two labels
    for line in raw_response.split("\n"):
        line = line.strip()
        if line.upper().startswith("SENTIMENT:"):
            # split(":", 1) only splits on the FIRST colon - so if the
            # summary line happens to contain a colon, it won't get cut wrong
            sentiment = line.split(":", 1)[1].strip().lower()
        elif line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()

    # Safety net: if what we parsed isn't exactly one of the three expected
    # values, default to "neutral" instead of returning something unexpected
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    # Save/refresh the cache entry so the next request within the TTL above
    # skips straight past the news fetch and Claude call entirely.
    if cached:
        cached.sentiment = sentiment
        cached.summary = summary
        cached.last_updated = datetime.utcnow()
    else:
        cached = SentimentCache(ticker=ticker, sentiment=sentiment, summary=summary)
        db.add(cached)
    db.commit()

    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "summary": summary
    }

# Checks whether a trade was made shortly after a sharp price move (up or
# down) - a proxy for an emotionally-driven entry rather than one based on
# careful research. Returns a dict with the flag and reasoning, or a
# "not enough data" fallback if history isn't available.
def check_fomo_for_trade(trade):
    if trade.action != "buy":
        return {"fomo_flag": False, "reason": "Only buy trades are checked for FOMO"}

    ticker = trade.ticker.upper()
    end_date = trade.trade_date
    start_date = end_date - timedelta(days=10)

    try:
        stock = yf.Ticker(ticker)
        history = stock.history(start=start_date.isoformat(), end=(end_date + timedelta(days=1)).isoformat())
    except Exception as e:
        print(f"yfinance history fetch failed for {ticker}: {e}")
        return {"fomo_flag": False, "reason": "Could not fetch price history"}

    if history.empty or len(history) < 2:
        return {"fomo_flag": False, "reason": "Not enough price history available to check"}

    price_at_trade = float(history["Close"].iloc[-1])
    lookback_index = max(0, len(history) - 6)
    price_before = float(history["Close"].iloc[lookback_index])

    percent_change = float(((price_at_trade - price_before) / price_before) * 100)

    FOMO_THRESHOLD = 8.0
    significant_move = bool(abs(percent_change) > FOMO_THRESHOLD)

    if significant_move and percent_change > 0:
        return {"fomo_flag": True, "reason": f"Stock rose {round(percent_change, 2)}% in the days before this trade - possible FOMO entry"}
    elif significant_move and percent_change < 0:
        return {"fomo_flag": True, "reason": f"Stock dropped {round(percent_change, 2)}% in the days before this trade - possible 'buying the dip'"}
    else:
        return {"fomo_flag": False, "reason": "No significant price move detected before this trade"}

# Aggregates reviewed trades to surface behavioral patterns: whether higher
# conviction actually correlates with better outcomes, and whether FOMO-flagged
# trades perform worse than non-FOMO ones. This is the ground-truth data layer
# a future AI-generated tendency summary will reason over.
# PROTECTED + SCOPED: only the logged-in user's own reviewed trades count.
@app.get("/trading-patterns")
def get_trading_patterns(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trades = db.query(Trade).filter(Trade.user_id == current_user.id).all()

    # Only trades that have actually been reviewed (outcome_tag set) count
    # toward the stats - everything else just gets counted as pending.
    reviewed = [t for t in trades if t.outcome_tag]
    pending = [t for t in trades if not t.outcome_tag]

    # --- Correct rate by conviction score ---
    # Groups reviewed trades by their conviction_score (1-5), tallying how
    # many landed in each outcome bucket, so we can see whether higher
    # conviction actually predicts correct calls.
    by_conviction = {}
    trades_missing_conviction = 0
    for t in reviewed:
        if t.conviction_score is None:
            trades_missing_conviction += 1
            continue
        score = t.conviction_score
        by_conviction.setdefault(score, {"correct": 0, "incorrect": 0, "mixed": 0, "total": 0})
        by_conviction[score][t.outcome_tag] += 1
        by_conviction[score]["total"] += 1

    conviction_breakdown = []
    for score in sorted(by_conviction.keys()):
        stats = by_conviction[score]
        correct_rate = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
        conviction_breakdown.append({
            "conviction_score": score,
            "total": stats["total"],
            "correct": stats["correct"],
            "incorrect": stats["incorrect"],
            "mixed": stats["mixed"],
            "correct_rate": round(correct_rate, 1)
        })

    # --- Correct rate: FOMO-flagged vs non-FOMO trades ---
    # Only "buy" trades are checked for FOMO (selling into a rally isn't FOMO -
    # same rule check_fomo_for_trade already applies), so sells are skipped here.
    # NOTE: this calls check_fomo_for_trade() once per reviewed buy trade, which
    # means a live yfinance lookup each time - fine for now, but worth caching
    # the FOMO result on the trade itself once there's real trade volume.
    fomo_stats = {"correct": 0, "incorrect": 0, "mixed": 0, "total": 0}
    non_fomo_stats = {"correct": 0, "incorrect": 0, "mixed": 0, "total": 0}

    for t in reviewed:
        if t.action != "buy":
            continue
        fomo_result = check_fomo_for_trade(t)
        target = fomo_stats if fomo_result["fomo_flag"] else non_fomo_stats
        target[t.outcome_tag] += 1
        target["total"] += 1

    def correct_rate(stats):
        return round((stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1)

    return {
        "reviewed_count": len(reviewed),
        "pending_count": len(pending),
        "trades_missing_conviction": trades_missing_conviction,
        "by_conviction": conviction_breakdown,
        "fomo_vs_non_fomo": {
            "fomo": {**fomo_stats, "correct_rate": correct_rate(fomo_stats)},
            "non_fomo": {**non_fomo_stats, "correct_rate": correct_rate(non_fomo_stats)}
        }
    }

# Creates a new user account. Rejects duplicate emails, hashes the password
# before it ever touches the database, and immediately returns a token so
# the frontend can log the user straight in without a separate login step.
@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: UserSignup, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    new_user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(new_user.id)
    return {"access_token": token}


# Verifies email + password against the stored hash, returns a fresh token
# on success. Deliberately returns the same generic error whether the email
# doesn't exist OR the password is wrong - never reveal which one it was,
# since that tells an attacker whether a given email has an account here.
@app.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(user.id)
    return {"access_token": token}


# Lets the frontend check "am I logged in, and as who" on app load, using
# whatever token is currently stored client-side.
@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}

# Saves or updates the logged-in user's survey answers. Same endpoint
# handles both the initial signup-survey submission and later edits from
# a settings page, since it's just "does a profile row already exist?"
@app.post("/profile")
def submit_profile(payload: ProfileSubmit, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    sectors_str = ",".join(payload.sectors_of_interest)
    trading_style_str = ",".join(payload.trading_style)

    if existing:
        existing.risk_tolerance = payload.risk_tolerance
        existing.investing_goals = payload.investing_goals
        existing.trading_style = trading_style_str
        existing.time_horizon = payload.time_horizon
        existing.income_bracket = payload.income_bracket
        existing.experience_level = payload.experience_level
        existing.sectors_of_interest = sectors_str
        existing.biggest_fear = payload.biggest_fear
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_profile = UserProfile(
            user_id=current_user.id,
            risk_tolerance=payload.risk_tolerance,
            investing_goals=payload.investing_goals,
            trading_style=trading_style_str,
            time_horizon=payload.time_horizon,
            income_bracket=payload.income_bracket,
            experience_level=payload.experience_level,
            sectors_of_interest=sectors_str,
            biggest_fear=payload.biggest_fear,
        )
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)
        return new_profile


# Returns the logged-in user's profile, or a 404 if they haven't completed
# the survey yet - the frontend uses this 404 as the signal to redirect to
# the survey instead of the dashboard.
@app.get("/profile")
def get_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "risk_tolerance": profile.risk_tolerance,
        "investing_goals": profile.investing_goals,
        "trading_style": profile.trading_style.split(","),
        "time_horizon": profile.time_horizon,
        "income_bracket": profile.income_bracket,
        "experience_level": profile.experience_level,
        "sectors_of_interest": profile.sectors_of_interest.split(","),
        "biggest_fear": profile.biggest_fear,
    }

class ChatMessageIn(BaseModel):
    message: str

# Gathers everything the advisor needs to answer grounded, personalized
# questions: the user's stated profile, current holdings, trading-pattern
# stats, and a sample of recent trades with their theses. Rebuilt fresh on
# every message, since holdings and patterns can change between questions.
def build_advisor_context(db: Session, current_user: User) -> str:
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    holdings_data = get_holdings(db=db, current_user=current_user)
    patterns_data = get_trading_patterns(db=db, current_user=current_user)

    recent_trades = (
        db.query(Trade)
        .filter(Trade.user_id == current_user.id)
        .order_by(Trade.trade_date.desc())
        .limit(10)
        .all()
    )

    profile_summary = "No profile on file." if not profile else f"""
Risk tolerance: {profile.risk_tolerance}
Investing goals: {profile.investing_goals}
Trading style: {profile.trading_style}
Time horizon: {profile.time_horizon}
Income bracket: {profile.income_bracket}
Experience level: {profile.experience_level}
Sectors of interest: {profile.sectors_of_interest}
Stated fear/mistake: {profile.biggest_fear or "not provided"}
"""

    holdings_summary = "\n".join(
        f"- {h['ticker']}: {h['shares']} shares, {h['percentage']}% of portfolio, "
        f"{'OVERWEIGHT' if h['overweight_flag'] else 'within limits'}, "
        f"all-time gain/loss {h['total_gain_loss_percent']}%"
        for h in holdings_data["holdings"]
    ) or "No current holdings."

    trades_summary = "\n".join(
    f"- {t.trade_date} {t.action.upper()} {t.ticker}: conviction "
    f"{f'{t.conviction_score}/5' if t.conviction_score else 'n/a'}, "
    f"{thesis.describe_trade_reason(t)}, outcome: {t.outcome_tag or 'not yet reviewed'}"
    + (f", reflection: \"{t.review_notes}\"" if t.review_notes else "")
    for t in recent_trades
) or "No trades logged yet."

    # Why the user trades, in their own words/categories - updated every
    # time they answer the thesis inbox, so the advisor's picture of their
    # habits stays current (see thesis.advisor_context_section).
    reasons_summary = thesis.advisor_context_section(db, current_user)

    patterns_summary = f"""
Reviewed trades: {patterns_data['reviewed_count']}, pending review: {patterns_data['pending_count']}
By conviction score: {patterns_data['by_conviction']}
FOMO-flagged trades correct rate: {patterns_data['fomo_vs_non_fomo']['fomo']['correct_rate']}%
Non-FOMO trades correct rate: {patterns_data['fomo_vs_non_fomo']['non_fomo']['correct_rate']}%
"""

    # NEW - per-holding fundamentals, so the advisor can reason about
    # valuation/quality (P/E, margins, growth) instead of just price and
    # gain/loss. Reads straight from PriceCache, which get_holdings() above
    # already populated a moment ago via get_or_fetch_price() for every
    # ticker - so this is a free DB read per holding, not a new yfinance call.
    def fmt(value, as_percent=False):
        if value is None:
            return "n/a"
        return f"{value * 100:.1f}%" if as_percent else f"{value:.2f}"

    fundamentals_lines = []
    for h in holdings_data["holdings"]:
        cached_price = db.query(PriceCache).filter(PriceCache.ticker == h["ticker"]).first()
        if not cached_price:
            continue
        fundamentals_lines.append(
            f"- {h['ticker']} ({cached_price.sector or 'unknown sector'}): "
            f"P/E {fmt(cached_price.pe_ratio)}, forward P/E {fmt(cached_price.forward_pe)}, "
            f"P/B {fmt(cached_price.price_to_book)}, "
            f"profit margin {fmt(cached_price.profit_margins, as_percent=True)}, "
            f"revenue growth {fmt(cached_price.revenue_growth, as_percent=True)}, "
            f"debt/equity {fmt(cached_price.debt_to_equity)}, "
            # dividendYield comes back from yfinance already as a plain
            # percentage (0.44 means 0.44%), unlike profit_margins/
            # revenue_growth which are 0-1 fractions - so no *100 here,
            # unlike the as_percent=True fields above.
            f"dividend yield {fmt(cached_price.dividend_yield) + '%' if cached_price.dividend_yield is not None else 'n/a'}"
        )
    fundamentals_summary = "\n".join(fundamentals_lines) or "No fundamentals data available."

    return f"""You are InnerStock's investing advisor.

Be conversational, practical, and concise. Match the depth of your answer to the user's question.

Default behavior:
- Keep answers under 120 words unless the user asks for more detail.
- Simple factual questions: 1–2 sentences.
- Portfolio questions: 2–5 short bullet points.
- Comparisons or explanations: 1–3 short paragraphs.
- Give detailed analysis only when the user explicitly requests it (e.g. "analyze", "explain in depth", "walk me through", or "give me a detailed report").

Use only the user's profile, holdings, fundamentals, trades, or behavioral patterns that are relevant to the current question. Don't force portfolio references into general investing questions.

If important information is missing, ask one brief clarifying question instead of making assumptions.

Response formatting:
- Use Markdown naturally.
- Start with a one-sentence direct answer.
- Use at most 2-3 headings only when they improve readability.
- Keep paragraphs to 1-2 sentences.
- Use bullet points for lists.
- Never center text or stack multiple bold headings.
- If giving a personalized insight, put it under a short "For your portfolio" section.

When relevant, help the user recognize patterns in their own investing behavior—such as concentration risk, FOMO, or conviction consistency—using their actual data.

The user's stated reasons for their trades (below) are the best evidence of how they actually invest. Compare what they say they do with what they do: e.g. which reasons tend to work for them, whether they often can't remember why they traded, or whether their stated style (profile) matches their real reasons. Treat reasons written in hindsight as less reliable.

Do not give generic investing advice. Ground your answers in the real data below whenever relevant. You are not a licensed financial advisor; make that clear if the user asks for concrete buy/sell recommendations.

=== USER PROFILE ===
{profile_summary}

=== CURRENT HOLDINGS ===
{holdings_summary}
Total portfolio value: ${holdings_data['total_value']:.2f}
Average conviction across positions: {holdings_data['avg_conviction']}/5

=== FUNDAMENTALS ===
{fundamentals_summary}

=== RECENT TRADES ===
{trades_summary}

=== BEHAVIORAL PATTERNS ===
{patterns_summary}

=== WHY THIS USER TRADES (their own stated reasons) ===
{reasons_summary}
"""

# The advisor chat. Saves the user's message, rebuilds full context fresh,
# sends the conversation history + context to Claude, saves and returns
# the reply. PROTECTED + SCOPED - only ever sees and stores this user's
# own data and conversation.
@app.post("/chat")
def chat(payload: ChatMessageIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Checked before saving anything, so a rate-limited message isn't
    # stored in history without a reply to go with it.
    enforce_ai_rate_limit(current_user.id, "chat")

    # Save the user's new message first - stored immediately, before we
    # even talk to Claude, so it's never lost even if something below fails.
    user_message = ChatMessage(user_id=current_user.id, role="user", content=payload.message)
    db.add(user_message)
    db.commit()

    # Pull recent conversation history (capped at 40, to avoid unbounded
    # token growth as a conversation gets long) so Claude has continuity
    # across turns - this is what gives the chatbot "memory."
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(40)
        .all()
    )

    # Rebuilt fresh every message (not cached) since holdings/stats can
    # change mid-conversation, e.g. if the user logs a new trade while chatting.
    context = build_advisor_context(db, current_user)

    # Reshape DB rows into the plain {role, content} format Claude's API
    # expects - strips out fields like id/created_at that Claude doesn't need.
    messages = [{"role": m.role, "content": m.content} for m in history]

    try:
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=context,       # background knowledge - invisible to the
                                   # user, shapes every answer without being
                                   # part of the visible conversation
            messages=messages,    # the actual back-and-forth, including
                                   # the new message just saved above
        )
        reply_text = response.content[0].text

        # Log real token usage and estimated cost for this call, so actual
        # spend can be tracked during testing instead of guessed at.
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        input_cost = (input_tokens / 1_000_000) * 1.00
        output_cost = (output_tokens / 1_000_000) * 5.00
        total_cost = input_cost + output_cost
        print(
            f"[chat cost] user_id={current_user.id} "
            f"input_tokens={input_tokens} output_tokens={output_tokens} "
            f"estimated_cost=${total_cost:.5f}"
        )

    except Exception as e:
        print(f"Claude API call failed for chat: {e}")
        raise HTTPException(status_code=500, detail="Could not generate a response right now")

    # Save Claude's reply too, tagged as "assistant" - this is what makes
    # it show up in history the NEXT time this function runs, which is how
    # the conversation actually persists and grows over time.
    assistant_message = ChatMessage(user_id=current_user.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    db.commit()

    # Frontend only needs the new reply here - it already has (or can
    # separately fetch) everything that came before.
    return {"reply": reply_text}


# Returns the full saved conversation for the logged-in user - no Claude
# call here at all, just reading back what's already stored. Used when the
# chat screen first loads, to show past messages from earlier sessions.
@app.get("/chat/history")
def get_chat_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {"messages": [{"role": m.role, "content": m.content} for m in messages]}

# Returns trades missing a thesis - the backlog of trades synced from a
# linked brokerage (see snaptrade_sync.py) that a user still needs to write
# a thesis for, distinct from
# /thesis-reviews which only shows trades whose review_date has passed.
@app.get("/trades/incomplete")
def get_incomplete_trades(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Same definition as the thesis inbox: no thesis AND no reason given
    # (a "don't remember" answer has reasons but no thesis text).
    trades = (
        db.query(Trade)
        .filter(*thesis.needs_reason_filter(current_user))
        .order_by(Trade.trade_date.desc())
        .all()
    )
    return {"trades": trades}


@app.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entries = db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()
    result = []
    for entry in entries:
        cached = get_or_fetch_price(entry.ticker, db)
        day_change_percent = None
        if cached and cached.previous_close and cached.current_price:
            day_change_percent = float((cached.current_price - cached.previous_close) / cached.previous_close * 100)
        result.append({
            "ticker": entry.ticker,
            "added_at": entry.added_at,
            "current_price": float(cached.current_price) if cached else None,
            "day_change_percent": day_change_percent,
        })
    return {"watchlist": result}


@app.post("/watchlist")
def add_to_watchlist(payload: WatchlistAdd, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = payload.ticker.upper()

    cached = get_or_fetch_price(ticker, db)
    if not cached:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or has no price data")

    existing = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id, Watchlist.ticker == ticker
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"'{ticker}' is already on your watchlist")

    entry = Watchlist(user_id=current_user.id, ticker=ticker)
    db.add(entry)
    db.commit()
    return {"success": True, "ticker": ticker}


@app.delete("/watchlist/{ticker}")
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = ticker.upper()
    entry = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id, Watchlist.ticker == ticker
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not on your watchlist")
    db.delete(entry)
    db.commit()
    return {"success": True}

@app.get("/stock/{ticker}/history")
def get_stock_history(ticker: str, range: str = "1M", db: Session = Depends(get_db)):
    range_map = {
        "1D": ("1d", "5m"),
        "1W": ("5d", "30m"),
        "1M": ("1mo", "1d"),
        "3M": ("3mo", "1d"),
        "1Y": ("1y", "1wk"),
        "ALL": ("max", "1mo"),
    }
    period, interval = range_map.get(range.upper(), ("1mo", "1d"))

    try:
        hist = yf.Ticker(ticker.upper()).history(period=period, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch history for '{ticker.upper()}'")

    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No history data for '{ticker.upper()}'")

    points = [
        {"date": ts.isoformat(), "close": float(row["Close"])}
        for ts, row in hist.iterrows()
    ]
    return {"ticker": ticker.upper(), "range": range.upper(), "points": points}