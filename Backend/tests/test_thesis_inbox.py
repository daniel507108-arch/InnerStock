# Tests for the "why did you make this trade?" inbox (thesis.py) and for the
# reasons flowing into the advisor's picture of the user.
from datetime import date, datetime, time, timedelta

import pytest

import main
from conftest import log_trade
from models import Trade, User

TODAY = date.today()


def user_id(db_session_factory, email="alice@example.com"):
    db = db_session_factory()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


def synced_trade(db_session_factory, uid, ticker="MUU.TO", action="buy", days_ago=3, quantity=20, price=6.64):
    """A trade as the brokerage sync creates it: no thesis, no reasons."""
    db = db_session_factory()
    trade = Trade(user_id=uid, ticker=ticker, action=action, quantity=quantity, price_per_share=price,
                  trade_date=TODAY - timedelta(days=days_ago), trade_time=time(14, 30),
                  source="snaptrade", external_id=f"activity:{ticker}-{action}-{days_ago}")
    db.add(trade)
    db.commit()
    trade_id = trade.id
    db.close()
    return trade_id


def get_trade(db_session_factory, trade_id):
    db = db_session_factory()
    try:
        return db.get(Trade, trade_id)
    finally:
        db.close()


def answer(client, headers, trade_ids, **fields):
    body = {"trade_ids": trade_ids, "reason_tags": ["dip_buy"], "thesis_text": "Pulled back 15% on no news",
            "conviction_score": 3, **fields}
    return client.put("/trades/thesis", headers=headers, json=body)


# --- The inbox --------------------------------------------------------------------------

def test_inbox_lists_only_unanswered_trades_newest_first(client, alice, db_session_factory):
    uid = user_id(db_session_factory)
    older = synced_trade(db_session_factory, uid, ticker="VFV.TO", days_ago=10)
    newer = synced_trade(db_session_factory, uid, ticker="MUU.TO", days_ago=1)
    log_trade(client, alice, "AAPL", "buy", 1, 100)  # logged by hand - already has a thesis

    inbox = client.get("/trades/needs-thesis", headers=alice).json()
    assert inbox["count"] == 2
    assert [t["id"] for t in inbox["trades"]] == [newer, older]
    assert client.get("/trades/needs-thesis/count", headers=alice).json() == {"count": 2}


def test_inbox_is_private(client, alice, bob, db_session_factory):
    synced_trade(db_session_factory, user_id(db_session_factory))
    assert client.get("/trades/needs-thesis", headers=bob).json()["count"] == 0
    assert client.get("/trades/needs-thesis").status_code == 401


def test_reason_catalog_has_separate_buy_and_sell_reasons(client, alice):
    catalog = client.get("/trades/reasons", headers=alice).json()
    buy_tags = {r["tag"] for r in catalog["buy"]}
    sell_tags = {r["tag"] for r in catalog["sell"]}
    assert {"dip_buy", "fomo", "dont_remember"} <= buy_tags
    assert {"take_profit", "panic", "dont_remember"} <= sell_tags
    assert "dip_buy" not in sell_tags


# --- Answering ---------------------------------------------------------------------------

def test_answering_saves_the_reason_and_clears_the_inbox(client, alice, db_session_factory):
    trade_id = synced_trade(db_session_factory, user_id(db_session_factory))
    review = (TODAY + timedelta(days=90)).isoformat()

    response = answer(client, alice, [trade_id], reason_tags=["dip_buy", "speculation"], conviction_score=2,
                      review_date=review)
    assert response.status_code == 200
    assert response.json() == {"updated": [trade_id], "remaining": 0}

    trade = get_trade(db_session_factory, trade_id)
    assert trade.reason_tags == "dip_buy,speculation"
    assert trade.thesis_text == "Pulled back 15% on no news"
    assert trade.conviction_score == 2
    assert trade.review_date.isoformat() == review
    assert trade.thesis_written_at is not None


def test_one_answer_can_cover_several_trades(client, alice, db_session_factory):
    uid = user_id(db_session_factory)
    ids = [synced_trade(db_session_factory, uid, days_ago=d) for d in (1, 2, 3)]
    response = answer(client, alice, ids, reason_tags=["dca"], thesis_text="Weekly automatic buy")
    assert sorted(response.json()["updated"]) == sorted(ids)
    assert client.get("/trades/needs-thesis/count", headers=alice).json()["count"] == 0


def test_answers_are_final(client, alice, db_session_factory):
    # No rewriting a reason after seeing how the trade turned out.
    trade_id = synced_trade(db_session_factory, user_id(db_session_factory))
    assert answer(client, alice, [trade_id]).status_code == 200
    response = answer(client, alice, [trade_id], thesis_text="Actually I always knew it would work")
    assert response.status_code == 409
    assert get_trade(db_session_factory, trade_id).thesis_text == "Pulled back 15% on no news"


def test_manual_trades_already_have_a_thesis_and_cannot_be_re_answered(client, alice):
    trade = log_trade(client, alice, "AAPL", "buy", 1, 100)
    assert answer(client, alice, [trade["id"]]).status_code == 409


def test_dont_remember_is_a_valid_answer_without_a_thesis(client, alice, db_session_factory):
    trade_id = synced_trade(db_session_factory, user_id(db_session_factory))
    response = answer(client, alice, [trade_id], reason_tags=["dont_remember"], thesis_text=None, conviction_score=None)
    assert response.status_code == 200
    trade = get_trade(db_session_factory, trade_id)
    assert trade.reason_tags == "dont_remember"
    assert trade.thesis_text is None
    assert client.get("/trades/needs-thesis/count", headers=alice).json()["count"] == 0


@pytest.mark.parametrize("fields, problem", [
    ({"reason_tags": ["take_profit"]}, "sell reason on a buy"),
    ({"reason_tags": ["made_up"]}, "unknown reason"),
    ({"reason_tags": ["dont_remember", "fomo"]}, "don't remember plus a reason"),
    ({"reason_tags": []}, "no reason"),
    ({"thesis_text": "because"}, "thesis too short"),
    ({"thesis_text": None}, "no thesis"),
    ({"conviction_score": None}, "no conviction"),
    ({"conviction_score": 6}, "conviction out of range"),
])
def test_invalid_answers_are_rejected(client, alice, db_session_factory, fields, problem):
    trade_id = synced_trade(db_session_factory, user_id(db_session_factory))
    response = answer(client, alice, [trade_id], **fields)
    assert response.status_code in (400, 422), problem
    assert get_trade(db_session_factory, trade_id).reason_tags is None


def test_buys_and_sells_need_separate_answers(client, alice, db_session_factory):
    uid = user_id(db_session_factory)
    buy = synced_trade(db_session_factory, uid, action="buy")
    sell = synced_trade(db_session_factory, uid, action="sell", days_ago=1)
    assert answer(client, alice, [buy, sell]).status_code == 400


def test_cannot_answer_someone_elses_trade(client, alice, bob, db_session_factory):
    alices = synced_trade(db_session_factory, user_id(db_session_factory))
    bobs = synced_trade(db_session_factory, user_id(db_session_factory, "bob@example.com"), days_ago=2)
    # Mixing in someone else's id rejects the whole request - nothing is saved.
    assert answer(client, bob, [bobs, alices]).status_code == 404
    assert get_trade(db_session_factory, alices).reason_tags is None
    assert get_trade(db_session_factory, bobs).reason_tags is None


# --- Manual trades ----------------------------------------------------------------------------

def test_logged_trades_can_carry_reasons(client, alice, db_session_factory):
    trade = log_trade(client, alice, "AAPL", "buy", 1, 100)
    assert get_trade(db_session_factory, trade["id"]).thesis_written_at is not None

    response = client.post("/trades", headers=alice, json={
        "ticker": "MSFT", "action": "sell", "quantity": 1, "price_per_share": 400,
        "trade_date": TODAY.isoformat(), "trade_time": "10:30:00", "thesis_text": "Locking in a 30% gain",
        "conviction_score": 4, "review_date": TODAY.isoformat(), "reason_tags": ["take_profit"],
    })
    assert response.status_code == 200
    assert response.json()["reason_tags"] == "take_profit"


def test_logged_trade_rejects_reason_for_wrong_action(client, alice):
    response = client.post("/trades", headers=alice, json={
        "ticker": "MSFT", "action": "buy", "quantity": 1, "price_per_share": 400,
        "trade_date": TODAY.isoformat(), "trade_time": "10:30:00", "thesis_text": "Cloud growth",
        "conviction_score": 4, "review_date": TODAY.isoformat(), "reason_tags": ["take_profit"],
    })
    assert response.status_code == 400


# --- How the user invests: summary + advisor ------------------------------------------------------

def test_summary_counts_reasons_and_their_outcomes(client, alice, db_session_factory):
    uid = user_id(db_session_factory)
    dip_1, dip_2, tip, forgot, waiting = (synced_trade(db_session_factory, uid, days_ago=d) for d in (1, 2, 3, 4, 5))
    answer(client, alice, [dip_1, dip_2], reason_tags=["dip_buy"], conviction_score=4)
    answer(client, alice, [tip], reason_tags=["tip_social"], thesis_text="Saw it on a Reddit thread", conviction_score=2)
    answer(client, alice, [forgot], reason_tags=["dont_remember"], thesis_text=None, conviction_score=None)
    client.patch(f"/trades/{dip_1}/outcome", headers=alice, json={"outcome_tag": "correct"})
    client.patch(f"/trades/{dip_2}/outcome", headers=alice, json={"outcome_tag": "incorrect"})

    summary = client.get("/trades/reasons-summary", headers=alice).json()
    assert summary["answered"] == 4
    assert summary["needs_reason"] == 1
    assert summary["dont_remember_count"] == 1
    assert summary["dont_remember_rate"] == 25.0
    dip = next(r for r in summary["by_reason"] if r["tag"] == "dip_buy")
    assert dip == {"action": "buy", "tag": "dip_buy", "label": "Bought the dip", "count": 2, "correct": 1,
                   "incorrect": 1, "mixed": 0, "avg_conviction": 4.0, "graded": 2, "correct_rate": 50.0,
                   "avg_return_pct": None, "avg_vs_market_pct": None}  # no price history in this test


def test_reasons_written_long_after_the_trade_count_as_hindsight(client, alice, db_session_factory):
    uid = user_id(db_session_factory)
    recent = synced_trade(db_session_factory, uid, days_ago=1)
    old = synced_trade(db_session_factory, uid, days_ago=60)
    answer(client, alice, [recent])
    answer(client, alice, [old])

    summary = client.get("/trades/reasons-summary", headers=alice).json()
    assert summary["hindsight_count"] == 1
    assert summary["hindsight_rate"] == 50.0


def test_answers_update_the_advisors_picture_of_the_user(client, alice, db_session_factory, prices):
    uid = user_id(db_session_factory)
    trade_id = synced_trade(db_session_factory, uid, ticker="LYTE")
    prices["LYTE"] = (14.0, 14.0)

    db = db_session_factory()
    user = db.get(User, uid)
    before = main.build_advisor_context(db, user)
    db.close()
    assert "hasn't given reasons for any trades yet" in before
    assert "LYTE: conviction n/a, no reason given yet" in before

    answer(client, alice, [trade_id], reason_tags=["tip_social"], thesis_text="Friend said it would squeeze",
           conviction_score=2)

    db = db_session_factory()
    after = main.build_advisor_context(db, db.get(User, uid))
    db.close()
    assert "=== WHY THIS USER TRADES" in after
    assert "Tip / social media: 1 trade(s), avg conviction 2.0/5" in after
    assert 'reasons: Tip / social media; thesis: "Friend said it would squeeze"' in after
