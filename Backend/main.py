# Import the main FastAPI class - this is the toolkit that lets us build a web server
from fastapi import FastAPI

# Import CORS middleware - this handles the "permission" between frontend and backend
from fastapi.middleware.cors import CORSMiddleware

# Import yfinance - lets us pull real stock data from Yahoo Finance
import yfinance as yf

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