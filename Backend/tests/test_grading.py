# Tests for the grading scorecard (grading.py): the price evidence shown
# when a trade comes back for review, the suggested grade, and the rule that
# grading against the numbers needs a written explanation.
from datetime import date, timedelta

import pytest

import grading
import main
from conftest import log_trade
from models import User

TODAY = date.today()
TRADED = TODAY - timedelta(days=30)
REVIEWED = TODAY - timedelta(days=10)


def closes(*points):
    """closes((days_after_trade, price), ...) -> [(date, price), ...]"""
    return [(TRADED + timedelta(days=d), price) for d, price in points]


def scorecard(client, headers, trade_id):
    response = client.get(f"/thesis-reviews/{trade_id}/scorecard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def grade(client, headers, trade_id, outcome, notes=None):
    return client.patch(f"/trades/{trade_id}/outcome", headers=headers,
                        json={"outcome_tag": outcome, "review_notes": notes})


# --- Suggested grades -----------------------------------------------------------------

@pytest.mark.parametrize("action, tags, ret, bench, expected", [
    ("buy", [], 20, 5, "correct"),        # made money and beat the market
    ("buy", [], -10, 5, "incorrect"),     # lost money and lagged the market
    ("buy", [], 4, 10, "mixed"),          # made money, but the index did better
    ("buy", [], -5, -15, "mixed"),        # lost money, but less than the market
    ("buy", [], 5, None, "correct"),      # no benchmark: judged on its own
    ("buy", [], 1, None, "mixed"),        # ...and a tiny move is a wash
    ("sell", ["take_profit"], -8, 2, "correct"),     # fell after you sold
    ("sell", ["take_profit"], 3, 6, "mixed"),        # rose, but less than the market
    ("sell", ["panic"], 15, 4, "incorrect"),         # ran away after you sold
])
def test_suggested_grade(action, tags, ret, bench, expected):
    assert grading.suggest_outcome(action, tags, ret, bench, "S&P 500")[0] == expected


def test_selling_for_cash_is_not_a_market_call():
    assert grading.suggest_outcome("sell", ["need_cash"], 30, 5, "S&P 500") is None
    assert grading.suggest_outcome("sell", ["need_cash", "panic"], 30, 5, "S&P 500")[0] == "incorrect"


def test_benchmark_matches_the_trades_currency():
    assert grading.benchmark_for("MUU.TO")[0] == "VFV.TO"
    assert grading.benchmark_for("LYTE.V")[0] == "VFV.TO"
    assert grading.benchmark_for("AAPL")[0] == "SPY"
    assert grading.benchmark_for("VFV.TO") is None  # it IS the S&P 500


# --- Scorecard ---------------------------------------------------------------------------

def test_scorecard_compares_the_trade_with_the_market(client, alice, history):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
    history["AAPL"] = closes((0, 100), (10, 110), (20, 120), (30, 90))
    history["SPY"] = closes((0, 400), (20, 420), (30, 400))

    card = scorecard(client, alice, trade["id"])
    assert card["available"] is True
    assert card["benchmark"] == {"ticker": "SPY", "label": "S&P 500"}
    assert card["return_now_pct"] == -10.0
    assert card["best_pct"] == 20.0 and card["worst_pct"] == -10.0
    assert card["series"][0] == {"date": TRADED.isoformat(), "close": 100.0}


def test_trades_are_judged_at_the_review_date_not_today(client, alice, history):
    # Up 20% at the review date the user picked, down 10% today. Waiting
    # longer to grade must not change the verdict either way.
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
    history["AAPL"] = closes((0, 100), (20, 120), (30, 90))
    history["SPY"] = closes((0, 400), (20, 420), (30, 400))

    card = scorecard(client, alice, trade["id"])
    assert card["judged_at"] == "review_date"
    assert card["at_review"]["date"] == REVIEWED.isoformat()
    assert card["return_pct"] == 20.0
    assert card["benchmark_return_pct"] == 5.0
    assert card["excess_pct"] == 15.0
    assert card["suggestion"]["outcome"] == "correct"


def test_scorecard_flags_fomo_entries(client, alice, history):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 120, trade_date=TRADED, review_date=REVIEWED)
    history["AAPL"] = [(TRADED - timedelta(days=d), p) for d, p in ((6, 100), (5, 102), (4, 108), (2, 112), (1, 118))] \
        + closes((0, 120), (20, 120))
    assert scorecard(client, alice, trade["id"])["fomo"]["fomo_flag"] is True


def test_stock_splits_dont_fake_a_loss(client, alice, history):
    # Bought at $500, then a 5:1 split: yfinance now shows the trade-day
    # close as $100. A rise to $110 is +10%, not -78%.
    trade = log_trade(client, alice, "AAPL", "buy", 1, 500, trade_date=TRADED, review_date=REVIEWED)
    history["AAPL"] = closes((0, 100), (20, 110))
    card = scorecard(client, alice, trade["id"])
    assert card["split_adjusted"] is True
    assert card["return_pct"] == 10.0


def test_scorecard_without_price_data_still_works(client, alice):
    trade = log_trade(client, alice, "ZZZZ", "buy", 1, 10, trade_date=TRADED, review_date=REVIEWED)
    card = scorecard(client, alice, trade["id"])
    assert card["available"] is False
    assert "graded from memory" in card["message"]


def test_scorecard_is_private(client, alice, bob, history):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
    assert client.get(f"/thesis-reviews/{trade['id']}/scorecard", headers=bob).status_code == 404
    assert client.get(f"/thesis-reviews/{trade['id']}/scorecard").status_code == 401


# --- Saving grades -----------------------------------------------------------------------

def test_grading_against_the_numbers_needs_a_note(client, alice, history):
    # Down 20% while the market rose 5% - the numbers say "incorrect".
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
    history["AAPL"] = closes((0, 100), (20, 80))
    history["SPY"] = closes((0, 400), (20, 420))

    response = grade(client, alice, trade["id"], "correct")
    assert response.status_code == 400
    assert "add a note" in response.json()["detail"]

    response = grade(client, alice, trade["id"], "correct", notes="Long-term thesis intact, short-term noise")
    assert response.status_code == 200

    recent = client.get("/thesis-reviews/recent", headers=alice).json()["reviews"][0]
    assert recent["graded_against_numbers"] is True
    assert recent["suggested_outcome"] == "incorrect"
    assert recent["graded_return_pct"] == -20.0
    assert recent["graded_benchmark_return_pct"] == 5.0


def test_agreeing_or_mixed_grades_need_no_note(client, alice, history):
    history["AAPL"] = closes((0, 100), (20, 80))
    history["SPY"] = closes((0, 400), (20, 420))
    for outcome in ("incorrect", "mixed"):
        trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
        assert grade(client, alice, trade["id"], outcome).status_code == 200


def test_trades_without_price_data_can_be_graded_from_memory(client, alice):
    trade = log_trade(client, alice, "ZZZZ", "buy", 1, 10, trade_date=TRADED, review_date=REVIEWED)
    assert grade(client, alice, trade["id"], "correct").status_code == 200
    recent = client.get("/thesis-reviews/recent", headers=alice).json()["reviews"][0]
    assert recent["graded_return_pct"] is None
    assert recent["graded_against_numbers"] is False


def test_unknown_grades_are_rejected(client, alice):
    trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED)
    assert grade(client, alice, trade["id"], "great").status_code == 400


def test_review_list_shows_why_the_trade_was_made(client, alice):
    log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED,
              reason_tags=["dip_buy", "valuation"])
    review = client.get("/thesis-reviews", headers=alice).json()["reviews"][0]
    assert [r["label"] for r in review["reasons"]] == ["Bought the dip", "Looked undervalued"]
    # Logged today for a trade made 30 days ago - so the reason was written in hindsight.
    assert review["written_in_hindsight"] is True


# --- Feeding back into "how the user invests" ------------------------------------------

def test_graded_returns_show_which_reasons_make_money(client, alice, history, db_session_factory):
    history["AAPL"] = closes((0, 100), (20, 120))
    history["SPY"] = closes((0, 400), (20, 420))
    for _ in range(2):
        trade = log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=TRADED, review_date=REVIEWED,
                          reason_tags=["dip_buy"])
        assert grade(client, alice, trade["id"], "correct").status_code == 200

    summary = client.get("/trades/reasons-summary", headers=alice).json()
    dip = next(r for r in summary["by_reason"] if r["tag"] == "dip_buy")
    assert dip["avg_return_pct"] == 20.0
    assert dip["avg_vs_market_pct"] == 15.0

    db = db_session_factory()
    user = db.query(User).filter(User.email == "alice@example.com").one()
    context = main.build_advisor_context(db, user)
    db.close()
    assert "avg return +20.0% (+15.0 pts vs S&P 500)" in context
    assert "outcome: correct (+20.0% vs S&P 500 +5.0%)" in context
