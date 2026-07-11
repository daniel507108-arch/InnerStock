# Import the main FastAPI class - this is the toolkit that lets us build a web server
from fastapi import FastAPI, Depends

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

# This defines exactly what fields a new trade submission must contain.
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

# A second route, specifically for testing the frontend-backend connection.
@app.get("/test")
def test_connection():
    return {"status": "connected", "data": "Hello from FastAPI!"}

# This route has {ticker} in the URL - that means the URL itself carries info.
# Visiting /stock/AAPL or /stock/TSLA both hit this same function, just with
# a different value for "ticker" each time.
@app.get("/stock/{ticker}")
def get_stock(ticker: str):
    # Ask yfinance for this specific company's data
    stock = yf.Ticker(ticker)
    info = stock.info

    # Pull out just the fields we actually need, and package them into
    # clean JSON. Yahoo's raw data has dozens of extra fields we don't need.
    return {
        "ticker": ticker,
        "price": info.get("currentPrice"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "sector": info.get("sector")
    }

# Creates a new trade. Takes JSON matching the TradeCreate shape above,
# saves it to the database, and returns the saved trade (now with an id).
@app.post("/trades")
def create_trade(trade: TradeCreate, db: Session = Depends(get_db)):
    new_trade = Trade(
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