# Import the main FastAPI class - this is the toolkit that lets us build a web server
from fastapi import FastAPI, Depends
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
from models import Trade, PriceCache
from datetime import date, datetime, timedelta

#FOR THE CLAUDE API
from dotenv import load_dotenv
import os
import anthropic

#FILE UPLOADING
from fastapi import UploadFile, File
import csv
import io

load_dotenv()

claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Create the actual app instance. Everything below attaches to this "app" object.
app = FastAPI()

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

    market_cap = info.get("marketCap")
    pe_ratio = info.get("trailingPE")
    sector = info.get("sector")

    if cached:
        cached.current_price = price
        cached.market_cap = market_cap
        cached.pe_ratio = pe_ratio
        cached.sector = sector
        cached.last_updated = datetime.utcnow()
    else:
        cached = PriceCache(
            ticker=ticker,
            current_price=price,
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
@app.post("/trades") # When front end sents POST request to /trades this will run
def create_trade(trade: TradeCreate, db: Session = Depends(get_db)): #Uses function get_db to open a connection to database
    new_trade = Trade( #CONSTRUCTOR
        user_id=1,  # hardcoded for now - matches your single-user MVP decision
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
@app.get("/trades")
def get_trades(db: Session = Depends(get_db)):
    return db.query(Trade).all()

# Puts all trades into current holdings, calculates each position's
# share of the total portfolio, and flags any position over 20%.
@app.get("/holdings")
def get_holdings(db: Session = Depends(get_db)):
    trades = db.query(Trade).all()

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
        value = shares * current_price
        total_value += value

        # NEW: calculate weighted average cost for this ticker
        bought_qty = cost_tracking[ticker]["total_bought_qty"]
        if bought_qty > 0:
            avg_cost = cost_tracking[ticker]["total_cost"] / bought_qty
        else:
            avg_cost = 0  # shouldn't normally happen, but guards against divide-by-zero

        holdings_list.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": current_price,
            "avg_cost": round(avg_cost, 2),
            "value": value
        })

    # Step 4: now that total_value is known, calculate each holding's % share
    for holding in holdings_list:
        if total_value > 0:
            percentage = (holding["value"] / total_value) * 100
        else:
            percentage = 0

        holding["percentage"] = round(percentage, 2)
        holding["overweight_flag"] = percentage > 20

    return {
        "holdings": holdings_list,
        "total_value": total_value
    }

# Uses Claude to generate a bull case, bear case, and key risk for a given
# ticker, based on data we already have cached (no new yfinance call needed).
@app.get("/bullbear/{ticker}")
def get_bull_bear(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper()  # normalize so "aapl" and "AAPL" match the same cache row

    # Look up this ticker's cached price data - we'll use it as context for Claude
    cached = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()

    # If we've never cached this ticker, there's no data to base the analysis on
    if not cached:
        return {"error": "No cached data for this ticker yet - visit /stock/{ticker} first"}

    # Build the actual prompt we'll send to Claude, injecting real cached
    # data directly into the text so the response is grounded in real numbers
    prompt = f"""Give a brief bull case, bear case, and key risk for {ticker} stock.
Current price: {cached.current_price}
Sector: {cached.sector}
P/E ratio: {cached.pe_ratio}
Market cap: {cached.market_cap}

Format your response as:
Bull Case: [1-2 sentences]
Bear Case: [1-2 sentences]
Key Risk: [1 sentence]"""

    # Send the prompt to Claude and wait for a response.
    # max_tokens caps how long the reply can be, keeping it short and cheap.
    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    # Claude's reply comes back as a list of content blocks - [0].text
    # grabs just the plain text of the first (and only) block here
    return {
        "ticker": ticker,
        "analysis": message.content[0].text
    }

# Accepts a CSV file upload, validates each row using the same rules as
# POST /trades, saves valid rows, and reports errors for invalid ones
# without rejecting the whole file.
@app.post("/trades/import")
async def import_trades(file: UploadFile = File(...), db: Session = Depends(get_db)):
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
                user_id=1,
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
@app.get("/thesis-reviews")
def get_thesis_reviews(db: Session = Depends(get_db)):
    today = date.today()
    due_trades = db.query(Trade).filter(
        Trade.review_date <= today,
        Trade.outcome_tag.is_(None)
    ).all()

    reviews = []
    for trade in due_trades:
        reviews.append({
            "id": trade.id,
            "ticker": trade.ticker,
            "action": trade.action,
            "thesis_text": trade.thesis_text,
            "conviction_score": trade.conviction_score,
            "trade_date": trade.trade_date.isoformat(),
            "review_date": trade.review_date.isoformat()
        })

    return {"reviews": reviews}


# Defines what a valid outcome update must look like
class OutcomeUpdate(BaseModel):
    outcome_tag: str  # expected: "correct", "incorrect", or "mixed"


# Updates one specific trade's outcome_tag. Once set, that trade stops
# showing up in GET /thesis-reviews above.
@app.patch("/trades/{trade_id}/outcome") #PATCH HTTP method updates something existing
def update_trade_outcome(trade_id: int, update: OutcomeUpdate, db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade with id {trade_id} not found")

    trade.outcome_tag = update.outcome_tag
    db.commit()

    return {"success": True, "id": trade_id, "outcome_tag": trade.outcome_tag}

# Pulls recent news headlines via yfinance, sends them to Claude for a
# single overall sentiment classification, and returns exactly one of:
# "positive", "neutral", "negative".
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

    # Even if the fetch didn't crash, there might just be no news at all
    # for this ticker - "not news_items" catches both None and an empty list []
    if not news_items:
        raise HTTPException(status_code=404, detail=f"No news available for ticker '{ticker}'")

    # Extract just the headline/title text from each news item.
    headlines = []
    for item in news_items[:5]:  # [:5] = "slicing" - only take the first 5 items
        # yfinance's news structure isn't always consistent - sometimes the
        # title is nested inside a "content" dict, sometimes it's at the top
        # level. Try the nested version first; if that's empty/missing,
        # "or" falls back to trying the flat version instead.
        title = item.get("content", {}).get("title") or item.get("title")
        if title:  # only keep it if we actually found a real title
            headlines.append(title)

    # It's possible news_items had entries, but none of them had a usable
    # title after our extraction attempts - guard against that too
    if not headlines:
        raise HTTPException(status_code=404, detail=f"No usable headlines found for ticker '{ticker}'")

    # Build the actual prompt text to send to Claude.
    # The tricky part: chr(10).join(f"- {h}" for h in headlines)
    #   - f"- {h}" for h in headlines  -> turns each headline into "- headline text"
    #   - chr(10) is just a newline character (same as writing "\n")
    #   - .join(...) glues all those bulleted lines together, one per line
    # End result: a clean bulleted list of headlines, like:
    #   - Apple announces new AI chip
    #   - iPhone sales beat expectations
    prompt = f"""Here are recent headlines about {ticker} stock:

{chr(10).join(f"- {h}" for h in headlines)}

Based on these headlines, classify the overall sentiment as exactly one word:
"positive", "neutral", or "negative". Respond with only that one word, nothing else."""

    # Send the prompt to Claude. max_tokens=10 is intentionally small since
    # we only expect a single word back, not a full explanation.
    try:
        message = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        # .strip() removes accidental leading/trailing spaces,
        # .lower() normalizes casing so "Positive" and "positive" match the same way
        sentiment = message.content[0].text.strip().lower()
    except Exception as e:
        print(f"Claude API call failed for {ticker} sentiment: {e}")
        raise HTTPException(status_code=404, detail="Could not generate sentiment analysis")

    # Safety net: even with strict instructions, an LLM might occasionally
    # return something unexpected (extra punctuation, a synonym, etc).
    # If it's not exactly one of our three expected values, default to
    # "neutral" instead of sending the frontend something it can't handle.
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    return {
        "ticker": ticker,
        "sentiment": sentiment
    }
