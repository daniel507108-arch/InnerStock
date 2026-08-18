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
from models import Trade, PriceCache, User, UserProfile, ChatMessage
from datetime import date, datetime, timedelta

#FOR THE CLAUDE API
from dotenv import load_dotenv
import os
import anthropic

#FILE UPLOADING
from fastapi import UploadFile, File
import csv
import io

# AUTH: registers a proper "bearer token" security scheme with FastAPI, so
# Swagger UI's Authorize button recognizes it and can attach the token
# automatically to every protected endpoint - instead of needing a raw
# header typed in manually on each one.
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

from auth import hash_password, verify_password, create_access_token, decode_access_token
from typing import List, Optional

# Create the actual app instance. Everything below attaches to this "app" object.
app = FastAPI()

bearer_scheme = HTTPBearer()

# CORS setup: by default, browsers block a webpage on one address (localhost:5173)
# from fetching data from a different address (localhost:8000) unless the second
# one explicitly allows it. This block gives that permission.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],  # only allow requests from our React app's address
    allow_methods=["*"],                       # allow all request types (GET, POST, etc.)
    allow_headers=["*"],                       # allow all header types
)

# This function creates a fresh database connection for each request,
# and closes it automatically when the request finishes - prevents
# connections from piling up unused.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# AUTH: Dependency for protected endpoints - decodes the token via FastAPI's
# HTTPBearer security scheme, looks up the matching user, and returns it.
# Raises 401 if the token is missing, invalid, or the user no longer exists.
# Defined here, right after get_db(), because Python needs this function to
# already exist before any endpoint below uses it as Depends(get_current_user).
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials  # HTTPBearer already strips the "Bearer " prefix for us

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

# This defines exactly what fields a new trade submission must contain, taken from Pydantic
# If someone sends data missing a required field or with the wrong type,
# FastAPI automatically rejects it with a clear error - before our code runs.
class TradeCreate(BaseModel):
    ticker: str
    action: str
    quantity: float
    price_per_share: float
    trade_date: date
    thesis_text: str
    conviction_score: int
    review_date: date

from pydantic import BaseModel, EmailStr

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
    trading_style: str
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

# Shared logic: returns cached price data if fresh, otherwise fetches from
# yfinance, saves it to the cache, and returns it. Used by both /stock/{ticker}
# and /holdings, so a holding never shows $0 just because nobody visited
# /stock/{ticker} for it first.
def get_or_fetch_price(ticker: str, db: Session):
    ticker = ticker.upper()

    cached = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()

    if cached and cached.last_updated:
        age = datetime.utcnow() - cached.last_updated
        if age < timedelta(minutes=15):
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

    price = info.get("currentPrice")
    if price is None:
        return cached  # invalid ticker or no data - same fallback

    previous_close = info.get("previousClose")
    market_cap = info.get("marketCap")
    pe_ratio = info.get("trailingPE")
    sector = info.get("sector")

    if cached:
        cached.current_price = price
        cached.previous_close = previous_close
        cached.market_cap = market_cap
        cached.pe_ratio = pe_ratio
        cached.sector = sector
        cached.last_updated = datetime.utcnow()
    else:
        cached = PriceCache(
            ticker=ticker,
            current_price=price,
            previous_close=previous_close,
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            sector=sector,
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

# Creates a new trade. Takes JSON matching the TradeCreate shape above,
# saves it to the database, and returns the saved trade (now with an id).
# PROTECTED + SCOPED: requires login, and the new trade is stamped with
# whoever's actually logged in - never trusted from the client, so no one
# can create a trade under someone else's account.
@app.post("/trades") # When front end sents POST request to /trades this will run
def create_trade(trade: TradeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): #Uses function get_db to open a connection to database
    new_trade = Trade( #CONSTRUCTOR
        user_id=current_user.id,  # taken from the logged-in user, not the client
        ticker=trade.ticker,
        action=trade.action,
        quantity=trade.quantity,
        price_per_share=trade.price_per_share,
        trade_date=trade.trade_date,
        thesis_text=trade.thesis_text,
        conviction_score=trade.conviction_score,
        review_date=trade.review_date,
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
@app.get("/holdings")
def get_holdings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trades = db.query(Trade).filter(Trade.user_id == current_user.id).all()

    # Step 1: tally net shares held per ticker (buys add, sells subtract)
    holdings = {}
    # NEW: separately track total cost and total quantity bought, for avg_cost.
    # Only "buy" trades count here - selling shares doesn't change the
    # average cost of the shares you still hold.
    cost_tracking = {}

    for trade in trades:
        ticker = trade.ticker.upper()
        if ticker not in holdings:
            holdings[ticker] = 0
        if ticker not in cost_tracking:
            cost_tracking[ticker] = {"total_cost": 0, "total_bought_qty": 0}

        if trade.action == "buy":
            holdings[ticker] += float(trade.quantity)
            # accumulate cost basis for this ticker
            cost_tracking[ticker]["total_cost"] += float(trade.quantity) * float(trade.price_per_share)
            cost_tracking[ticker]["total_bought_qty"] += float(trade.quantity)
        elif trade.action == "sell":
            holdings[ticker] -= float(trade.quantity)

    # Step 2: drop any ticker fully sold out (0 or negative shares left)
    holdings = {ticker: shares for ticker, shares in holdings.items() if shares > 0}

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

        # NEW: calculate weighted average cost for this ticker
        bought_qty = cost_tracking[ticker]["total_bought_qty"]
        if bought_qty > 0:
            avg_cost = cost_tracking[ticker]["total_cost"] / bought_qty
        else:
            avg_cost = 0  # shouldn't normally happen, but guards against divide-by-zero

        # NEW: all-time gain/loss - compares current price to what you paid
        # on average, across the whole time you've held this position
        total_gain_loss = (current_price - avg_cost) * shares
        total_gain_loss_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

        # NEW: today's gain/loss - compares current price to yesterday's
        # close, regardless of when you actually bought in. This is what
        # lets the frontend toggle between "today" and "all-time" views
        # without needing a second API call - both numbers are always here.
        day_gain_loss = (current_price - previous_close) * shares
        day_gain_loss_percent = ((current_price - previous_close) / previous_close * 100) if previous_close > 0 else 0

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
        if ticker in holdings and trade.action == "buy":
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
    # yesterday's portfolio value, which is the correct denominator for %.
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
# NOT user-scoped - stock-level analysis, not tied to a specific portfolio.
@app.get("/bullbear/{ticker}")
def get_bull_bear(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper()

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

# Accepts a CSV file upload, validates each row using the same rules as
# POST /trades, saves valid rows, and reports errors for invalid ones
# without rejecting the whole file.
# PROTECTED + SCOPED: every imported trade is stamped with the logged-in
# user's id, same as POST /trades.
@app.post("/trades/import")
async def import_trades(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    contents = await file.read()
    decoded = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    successful_count = 0
    errors = []

    # enumerate starting at 1, matching "first data row = row 1" (header doesn't count)
    for row_num, row in enumerate(reader, start=1):
        try:
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                raise ValueError("ticker must not be empty")

            action = (row.get("action") or "").strip().lower()
            if action not in ("buy", "sell"):
                raise ValueError('action must be "buy" or "sell"')

            try:
                quantity = float(row.get("quantity"))
            except (ValueError, TypeError):
                raise ValueError("quantity must be a number")
            if quantity <= 0:
                raise ValueError("quantity must be greater than 0")

            try:
                price_per_share = float(row.get("price_per_share"))
            except (ValueError, TypeError):
                raise ValueError("price_per_share must be a number")
            if price_per_share <= 0:
                raise ValueError("price_per_share must be greater than 0")

            try:
                trade_date = date.fromisoformat((row.get("trade_date") or "").strip())
            except ValueError:
                raise ValueError("trade_date must be a valid date (YYYY-MM-DD)")

            thesis_text = (row.get("thesis_text") or "").strip()
            if not thesis_text:
                raise ValueError("thesis_text must not be empty")

            try:
                conviction_score = int(row.get("conviction_score"))
            except (ValueError, TypeError):
                raise ValueError("conviction_score must be an integer")
            if conviction_score < 1 or conviction_score > 5:
                raise ValueError("conviction_score must be between 1 and 5")

            try:
                review_date = date.fromisoformat((row.get("review_date") or "").strip())
            except ValueError:
                raise ValueError("review_date must be a valid date (YYYY-MM-DD)")

            # all checks passed - save this row
            new_trade = Trade(
                user_id=current_user.id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                price_per_share=price_per_share,
                trade_date=trade_date,
                thesis_text=thesis_text,
                conviction_score=conviction_score,
                review_date=review_date,
            )
            db.add(new_trade)
            db.commit()
            successful_count += 1

        except ValueError as e:
            db.rollback()  # undo any partial change for this failed row
            errors.append({"row": row_num, "message": str(e)})

    return {
        "successful_count": successful_count,
        "errors": errors
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
@app.get("/sentiment/{ticker}") 
def get_sentiment(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper()  # normalize, same habit as our other stock routes

    # Ask yfinance for recent news articles about this ticker.
    # stock.news is a DIFFERENT dataset than stock.info - this one returns
    # a list of news article dictionaries, not price/fundamentals data.
    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news
    except Exception as e:
        print(f"yfinance news fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not fetch news for ticker '{ticker}'")

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
    for t in reviewed:
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

    if existing:
        existing.risk_tolerance = payload.risk_tolerance
        existing.investing_goals = payload.investing_goals
        existing.trading_style = payload.trading_style
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
            trading_style=payload.trading_style,
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
        "trading_style": profile.trading_style,
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
    f"- {t.trade_date} {t.action.upper()} {t.ticker}: conviction {t.conviction_score}/5, "
    f"thesis: \"{t.thesis_text}\", outcome: {t.outcome_tag or 'not yet reviewed'}"
    + (f", reflection: \"{t.review_notes}\"" if t.review_notes else "")
    for t in recent_trades
) or "No trades logged yet."

    patterns_summary = f"""
Reviewed trades: {patterns_data['reviewed_count']}, pending review: {patterns_data['pending_count']}
By conviction score: {patterns_data['by_conviction']}
FOMO-flagged trades correct rate: {patterns_data['fomo_vs_non_fomo']['fomo']['correct_rate']}%
Non-FOMO trades correct rate: {patterns_data['fomo_vs_non_fomo']['non_fomo']['correct_rate']}%
"""

    return f"""You are InnerStock's investing advisor.

Be conversational, practical, and concise. Match the depth of your answer to the user's question.

Default behavior:
- Keep answers under 120 words unless the user asks for more detail.
- Simple factual questions: 1–2 sentences.
- Portfolio questions: 2–5 short bullet points.
- Comparisons or explanations: 1–3 short paragraphs.
- Give detailed analysis only when the user explicitly requests it (e.g. "analyze", "explain in depth", "walk me through", or "give me a detailed report").

Use only the user's profile, holdings, trades, or behavioral patterns that are relevant to the current question. Don't force portfolio references into general investing questions.

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

Do not give generic investing advice. Ground your answers in the real data below whenever relevant. You are not a licensed financial advisor; make that clear if the user asks for concrete buy/sell recommendations.

=== USER PROFILE ===
{profile_summary}

=== CURRENT HOLDINGS ===
{holdings_summary}
Total portfolio value: ${holdings_data['total_value']:.2f}
Average conviction across positions: {holdings_data['avg_conviction']}/5

=== RECENT TRADES ===
{trades_summary}

=== BEHAVIORAL PATTERNS ===
{patterns_summary}
"""

# The advisor chat. Saves the user's message, rebuilds full context fresh,
# sends the conversation history + context to Claude, saves and returns
# the reply. PROTECTED + SCOPED - only ever sees and stores this user's
# own data and conversation.
@app.post("/chat")
def chat(payload: ChatMessageIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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