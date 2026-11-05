# Shared test setup. Every test gets:
#   - a brand-new, empty in-memory SQLite database (nothing touches your
#     real innerstock.db, and tests can't leak data into each other)
#   - fake stock prices instead of real yfinance calls (fast, deterministic,
#     works offline and in CI)
#   - fake API keys, so a test can never accidentally spend real Claude money
import os

# Must be set BEFORE main/config are imported - config.py reads these at
# import time. load_dotenv() never overrides variables that already exist,
# so these win over anything in a developer's local .env.
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from database import Base


@pytest.fixture
def db_session_factory():
    # StaticPool + check_same_thread=False keeps ONE shared connection, so
    # the in-memory database survives across the threads TestClient uses.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def prices(monkeypatch):
    """Fake price table. Tests fill it in: prices["AAPL"] = (current, previous_close).

    Replaces get_or_fetch_price, the one helper every route uses for prices,
    so /holdings and /watchlist never reach yfinance. A ticker that isn't in
    the table behaves like a failed yfinance lookup (returns None).
    """
    table = {}

    def fake_get_or_fetch_price(ticker, db):
        ticker = ticker.upper()
        if ticker not in table:
            return None
        current, previous_close = table[ticker]
        return SimpleNamespace(ticker=ticker, current_price=current, previous_close=previous_close)

    monkeypatch.setattr(main, "get_or_fetch_price", fake_get_or_fetch_price)
    return table


@pytest.fixture
def client(db_session_factory, prices, monkeypatch):
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    # /thesis-reviews runs a FOMO check that downloads price history from
    # yfinance - stub it out so tests stay offline.
    monkeypatch.setattr(
        main, "check_fomo_for_trade", lambda trade: {"fomo_flag": False, "reason": "stubbed in tests"}
    )

    main.app.dependency_overrides[main.get_db] = override_get_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def signup(client, email, name="Test User", password="password123"):
    """Creates a user and returns ready-to-use auth headers for them."""
    response = client.post("/auth/signup", json={"name": name, "email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com", name="Alice")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com", name="Bob")


LONG_AGO = date.today() - timedelta(days=30)


def log_trade(client, headers, ticker, action, quantity, price, trade_date=LONG_AGO,
              conviction=3, review_date=None):
    """Logs a trade through the real POST /trades endpoint and returns its JSON."""
    response = client.post("/trades", headers=headers, json={
        "ticker": ticker,
        "action": action,
        "quantity": quantity,
        "price_per_share": price,
        "trade_date": trade_date.isoformat(),
        "trade_time": "10:30:00",
        "thesis_text": f"Test thesis for {ticker}",
        "conviction_score": conviction,
        "review_date": (review_date or date.today() + timedelta(days=30)).isoformat(),
    })
    assert response.status_code == 200, response.text
    return response.json()
