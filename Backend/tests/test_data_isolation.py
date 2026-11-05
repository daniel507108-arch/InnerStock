# Tests that one user can never see or change another user's data, and
# that protected routes reject requests without a valid login.
#
# Pattern: Alice creates data, then Bob (a second, separate account) tries
# to read or modify it. Every protected route filters by current_user.id -
# these tests are what catch it if a new or edited route forgets to.
from datetime import date, timedelta

import pytest

import main
from auth import create_access_token
from conftest import log_trade, signup
from models import ChatMessage

PAST = date.today() - timedelta(days=5)


# --- Authentication -----------------------------------------------------------

PROTECTED_GET_ROUTES = [
    "/trades",
    "/holdings",
    "/thesis-reviews",
    "/thesis-reviews/recent",
    "/trades/incomplete",
    "/trading-patterns",
    "/profile",
    "/chat/history",
    "/watchlist",
    "/auth/me",
]


@pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
def test_protected_routes_reject_missing_token(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
def test_protected_routes_reject_forged_token(client, path):
    headers = {"Authorization": "Bearer not-a-real-token"}
    assert client.get(path, headers=headers).status_code == 401


def test_token_for_nonexistent_user_is_rejected(client):
    # Validly signed token, but for a user id that doesn't exist (e.g. after
    # a database reset) - must be a 401, not a crash or someone else's data.
    headers = {"Authorization": f"Bearer {create_access_token(9999)}"}
    assert client.get("/trades", headers=headers).status_code == 401


def test_login_with_wrong_password_fails(client, alice):
    response = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_signup_with_duplicate_email_fails(client, alice):
    response = client.post("/auth/signup", json={
        "name": "Impostor", "email": "alice@example.com", "password": "password123",
    })
    assert response.status_code == 400


# --- Trades -------------------------------------------------------------------

def test_users_only_see_their_own_trades(client, alice, bob):
    log_trade(client, alice, "AAPL", "buy", 10, 100)
    log_trade(client, bob, "MSFT", "buy", 1, 400)

    alice_trades = client.get("/trades", headers=alice).json()
    bob_trades = client.get("/trades", headers=bob).json()

    assert [t["ticker"] for t in alice_trades] == ["AAPL"]
    assert [t["ticker"] for t in bob_trades] == ["MSFT"]


def test_trade_owner_comes_from_token_not_request_body(client, alice, bob):
    # Bob tries to slip Alice's user_id into the request body. The trade
    # must still belong to Bob (whoever's token it is), not Alice.
    alice_id = client.get("/auth/me", headers=alice).json()["id"]
    response = client.post("/trades", headers=bob, json={
        "user_id": alice_id,
        "ticker": "AAPL", "action": "buy", "quantity": 1, "price_per_share": 100,
        "trade_date": PAST.isoformat(), "trade_time": "10:30:00",
        "thesis_text": "sneaky", "conviction_score": 3,
        "review_date": PAST.isoformat(),
    })
    assert response.status_code == 200
    assert client.get("/trades", headers=alice).json() == []
    assert len(client.get("/trades", headers=bob).json()) == 1


def test_users_only_see_their_own_holdings(client, alice, bob, prices):
    prices["AAPL"] = (100, 100)
    log_trade(client, alice, "AAPL", "buy", 10, 100)

    assert client.get("/holdings", headers=bob).json()["holdings"] == []


def test_cannot_grade_another_users_trade(client, alice, bob):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, review_date=PAST)

    response = client.patch(f"/trades/{trade['id']}/outcome", headers=bob,
                            json={"outcome_tag": "incorrect", "review_notes": "tampered"})
    assert response.status_code == 404

    # Alice's trade is untouched - still waiting for her to grade it.
    reviews = client.get("/thesis-reviews", headers=alice).json()["reviews"]
    assert [r["id"] for r in reviews] == [trade["id"]]


def test_owner_can_grade_their_own_trade(client, alice):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, review_date=PAST)

    response = client.patch(f"/trades/{trade['id']}/outcome", headers=alice,
                            json={"outcome_tag": "correct", "review_notes": "played out"})
    assert response.status_code == 200

    # Graded trades leave the "due" list and show up in "recent".
    assert client.get("/thesis-reviews", headers=alice).json()["reviews"] == []
    recent = client.get("/thesis-reviews/recent", headers=alice).json()
    assert "correct" in str(recent)


def test_thesis_reviews_are_scoped(client, alice, bob):
    log_trade(client, alice, "AAPL", "buy", 10, 100, review_date=PAST)

    assert client.get("/thesis-reviews", headers=bob).json()["reviews"] == []


def test_incomplete_trades_are_scoped(client, alice, bob):
    csv_data = (
        "activity_type,activity_sub_type,symbol,quantity,unit_price,description,effective_at\n"
        "Trade,BUY,AAPL,5,100,FX Rate: 1.0,2026-01-15T10:00:00-05:00\n"
    )
    client.post("/trades/import/wealthsimple", headers=alice,
                files={"file": ("export.csv", csv_data, "text/csv")})

    assert len(client.get("/trades/incomplete", headers=alice).json()["trades"]) == 1
    assert client.get("/trades/incomplete", headers=bob).json()["trades"] == []


# --- Watchlist, chat, profile ---------------------------------------------------

def test_cannot_remove_another_users_watchlist_entry(client, alice, bob, prices):
    prices["AAPL"] = (100, 100)
    assert client.post("/watchlist", headers=alice, json={"ticker": "AAPL"}).status_code == 200

    assert client.get("/watchlist", headers=bob).json()["watchlist"] == []
    assert client.delete("/watchlist/AAPL", headers=bob).status_code == 404
    assert [w["ticker"] for w in client.get("/watchlist", headers=alice).json()["watchlist"]] == ["AAPL"]


def test_chat_history_is_scoped(client, alice, bob, db_session_factory):
    alice_id = client.get("/auth/me", headers=alice).json()["id"]
    db = db_session_factory()
    db.add(ChatMessage(user_id=alice_id, role="user", content="my private question"))
    db.commit()
    db.close()

    assert len(client.get("/chat/history", headers=alice).json()["messages"]) == 1
    assert client.get("/chat/history", headers=bob).json()["messages"] == []


def test_profile_is_scoped(client, alice, bob):
    response = client.post("/profile", headers=alice, json={
        "risk_tolerance": "high", "investing_goals": "growth",
        "trading_style": ["swing"], "time_horizon": "5y_plus",
        "income_bracket": "50k_100k", "experience_level": "intermediate",
        "sectors_of_interest": ["tech"], "biggest_fear": "a crash",
    })
    assert response.status_code == 200, response.text

    assert client.get("/profile", headers=alice).status_code == 200
    assert client.get("/profile", headers=bob).status_code == 404
