# Tests for the SnapTrade (Wealthsimple) sync and the /brokerage routes.
#
# A FakeSnapTrade client stands in for the real API (no network, no keys),
# and the USD/CAD lookup is stubbed to a fixed 1.25 so currency conversion
# is predictable. Records are shaped like real SnapTrade responses.
from datetime import date, time

import pytest

import snaptrade_sync
from models import BrokerageAccount, Trade, User

FX_RATE = 1.25  # CAD per USD in these tests

ACCOUNTS = [
    {"id": "acct-tfsa", "kind": "investment", "raw_type": "TFSA", "display_name": "Wealthsimple Trade TFSA"},
    {"id": "acct-personal", "kind": "investment", "raw_type": "PERSONAL", "display_name": "Wealthsimple Trade PERSONAL"},
    {"id": "acct-crypto", "kind": "investment", "raw_type": "CRYPTO", "display_name": "Wealthsimple Trade CRYPTO"},
    {"id": "acct-cash", "kind": "deposit", "raw_type": "MSB", "display_name": "Wealthsimple Trade MSB"},
]


def activity(id, symbol, type_, units, price, when, currency="CAD", security_currency="CAD", option=None):
    return {
        "id": id, "type": type_, "units": units, "price": price, "trade_date": when,
        "currency": {"code": currency}, "option_symbol": option,
        "symbol": {"symbol": symbol, "currency": {"code": security_currency}},
    }


def order(id, symbol, action, qty, price, when, quote_currency="CAD", security_currency="CAD", status="EXECUTED"):
    return {
        "brokerage_order_id": id, "status": status, "action": action,
        "filled_quantity": str(qty), "execution_price": str(price), "time_executed": when,
        "quote_currency": {"code": quote_currency}, "option_symbol": None,
        "universal_symbol": {"symbol": symbol, "currency": {"code": security_currency}},
    }


class FakeSnapTrade:
    """Stand-in for the SnapTrade SDK client.

    Data is keyed by SnapTrade user id: None = the personal-key user (no
    per-user credentials are sent); a string = a registered commercial-mode
    user. Every call records the credentials it was made with, so tests can
    prove each request carried the right user's id + secret.
    """

    def __init__(self):
        self.accounts = {None: ACCOUNTS}  # snaptrade user id -> account list
        self.activities = {}   # account id -> list of activity dicts
        self.orders = {}       # account id -> list of order dicts
        self.calls = 0
        self.credentials_seen = []   # (method, user_id, user_secret)
        self.registered = {}         # snaptrade user id -> secret
        self.deleted = []
        outer = self

        def record(method, kwargs):
            outer.calls += 1
            outer.credentials_seen.append((method, kwargs.get("user_id"), kwargs.get("user_secret")))
            user_id = kwargs.get("user_id")
            if user_id is not None and outer.registered.get(user_id) != kwargs.get("user_secret"):
                raise RuntimeError("401 invalid user secret")
            return user_id

        class AccountInformation:
            def list_all_user_accounts(self, **kwargs):
                user_id = record("list_all_user_accounts", kwargs)
                return {"results": outer.accounts.get(user_id, [])}

            def get_account_activities(self, account_id, type, offset, limit, start_date=None, **kwargs):
                record("get_account_activities", kwargs)
                data = outer.activities.get(account_id, [])
                return {"data": data[offset:offset + limit], "pagination": {"total": len(data)}}

            def get_user_account_recent_orders(self, account_id, only_executed, **kwargs):
                record("get_user_account_recent_orders", kwargs)
                return {"orders": outer.orders.get(account_id, [])}

        class Authentication:
            def login_snap_trade_user(self, connection_type, **kwargs):
                record("login_snap_trade_user", kwargs)
                return {"redirectURI": "https://app.snaptrade.example/portal?session=abc", "sessionId": "abc"}

            def register_snap_trade_user(self, user_id):
                outer.registered[user_id] = f"secret-for-{user_id}"
                return {"userId": user_id, "userSecret": outer.registered[user_id]}

            def delete_snap_trade_user(self, user_id):
                outer.deleted.append(user_id)
                outer.registered.pop(user_id, None)
                return {"status": "deleted"}

        self.account_information = AccountInformation()
        self.authentication = Authentication()


@pytest.fixture
def fake_snaptrade(monkeypatch):
    fake = FakeSnapTrade()
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SNAPTRADE_OWNER_EMAIL", "alice@example.com")
    monkeypatch.setattr(snaptrade_sync, "get_client", lambda: fake)
    monkeypatch.setattr(snaptrade_sync, "usd_cad_rates", lambda dates: {d: FX_RATE for d in dates})
    return fake


def sync(client, headers, force=True):
    response = client.post(f"/brokerage/sync?force={'true' if force else 'false'}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def all_trades(db_session_factory):
    db = db_session_factory()
    try:
        return db.query(Trade).order_by(Trade.trade_date, Trade.id).all()
    finally:
        db.close()


def alice_id(db_session_factory):
    db = db_session_factory()
    try:
        return db.query(User).filter(User.email == "alice@example.com").one().id
    finally:
        db.close()


def add_trade(db_session_factory, **fields):
    db = db_session_factory()
    db.add(Trade(**fields))
    db.commit()
    db.close()


# --- Access control ---------------------------------------------------------------

def test_status_unavailable_when_keys_missing(client, alice, monkeypatch):
    monkeypatch.delenv("SNAPTRADE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SNAPTRADE_CONSUMER_KEY", raising=False)
    monkeypatch.setenv("SNAPTRADE_OWNER_EMAIL", "alice@example.com")
    assert client.get("/brokerage/status", headers=alice).json() == {"available": False}
    assert client.post("/brokerage/sync", headers=alice).status_code == 403


def test_only_key_owner_can_use_brokerage(client, alice, bob, fake_snaptrade):
    # The personal key reads Alice's brokerage - Bob must not be able to
    # pull her trades into his account, or even start a connection.
    assert client.get("/brokerage/status", headers=bob).json() == {"available": False}
    assert client.post("/brokerage/sync", headers=bob).status_code == 403
    assert client.post("/brokerage/connect", headers=bob).status_code == 403
    assert client.get("/brokerage/status", headers=alice).json()["available"] is True


def test_routes_require_login(client):
    assert client.get("/brokerage/status").status_code == 401
    assert client.post("/brokerage/sync").status_code == 401


def test_connect_returns_portal_link(client, alice, fake_snaptrade):
    response = client.post("/brokerage/connect", headers=alice)
    assert response.status_code == 200
    assert response.json()["redirect_uri"].startswith("https://app.snaptrade.example/portal")


# --- Importing trades ----------------------------------------------------------------

def test_first_sync_imports_trades(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z"),
        activity("a2", "VFV.TO", "SELL", -4, 155.0, "2026-03-05T15:00:00Z"),  # sells come through negative
    ]
    fake_snaptrade.activities["acct-personal"] = [
        activity("a3", "ZIGY.VN", "BUY", 61.3496, 1.63, "2026-03-03T18:16:35Z"),
    ]

    result = sync(client, alice)
    assert result["new_trades"] == 3
    assert result["accounts"] == ["Wealthsimple Trade TFSA", "Wealthsimple Trade PERSONAL"]

    trades = all_trades(db_session_factory)
    assert [(t.ticker, t.action, float(t.quantity)) for t in trades] == [
        ("VFV.TO", "buy", 10), ("ZIGY.V", "buy", 61.3496), ("VFV.TO", "sell", 4),
    ]
    assert all(t.source == "snaptrade" and t.thesis_text is None for t in trades)
    assert trades[0].external_id == "activity:a1"


def test_tsx_venture_suffix_is_mapped_for_yfinance(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "ZIGY.VN", "BUY", 5, 1.5, "2026-03-02T15:00:00Z")]
    sync(client, alice)
    assert all_trades(db_session_factory)[0].ticker == "ZIGY.V"


def test_timestamps_are_converted_to_market_time(client, alice, fake_snaptrade, db_session_factory):
    # 02:30 UTC on Mar 3 is 21:30 the previous evening in New York.
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "VFV.TO", "BUY", 1, 150.0, "2026-03-03T02:30:00Z")]
    sync(client, alice)
    trade = all_trades(db_session_factory)[0]
    assert trade.trade_date == date(2026, 3, 2)
    assert trade.trade_time == time(21, 30)


def test_us_stock_price_is_converted_from_cad_to_usd(client, alice, fake_snaptrade, db_session_factory):
    # Wealthsimple reports US trades with the price already in CAD.
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "NOW", "BUY", 1, 137.5, "2026-03-02T15:00:00Z", currency="CAD", security_currency="USD"),
        activity("a2", "COHR", "BUY", 1, 90.0, "2026-03-02T15:00:00Z", currency="USD", security_currency="USD"),
    ]
    sync(client, alice)
    prices = {t.ticker: float(t.price_per_share) for t in all_trades(db_session_factory)}
    assert prices["NOW"] == pytest.approx(110.0)   # 137.50 CAD / 1.25
    assert prices["COHR"] == pytest.approx(90.0)   # already USD, untouched


def test_missing_fx_rate_skips_trade_instead_of_storing_wrong_currency(client, alice, fake_snaptrade, monkeypatch, db_session_factory):
    monkeypatch.setattr(snaptrade_sync, "usd_cad_rates", lambda dates: {})
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "NOW", "BUY", 1, 137.5, "2026-03-02T15:00:00Z", security_currency="USD"),
    ]
    result = sync(client, alice)
    assert result["new_trades"] == 0
    assert len(result["errors"]) == 1
    assert all_trades(db_session_factory) == []


def test_options_are_skipped(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "COHR", "BUY", 1, 5.73, "2026-03-02T15:00:00Z", option={"ticker": "COHR 261113C00275000"}),
    ]
    result = sync(client, alice)
    assert result["new_trades"] == 0
    assert result["skipped"] == ["BUY COHR"]
    assert all_trades(db_session_factory) == []


def test_resync_does_not_duplicate(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]
    sync(client, alice)
    result = sync(client, alice)
    assert result["new_trades"] == 0
    assert result["already_synced"] == 1
    assert len(all_trades(db_session_factory)) == 1


# --- Accounts -------------------------------------------------------------------------

def test_only_tfsa_and_personal_sync_by_default(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-crypto"] = [activity("c1", "BTC", "BUY", 0.01, 90000, "2026-03-02T15:00:00Z")]
    sync(client, alice)

    detail = {a["account_type"]: a["sync_enabled"] for a in client.get("/brokerage/status", headers=alice).json()["accounts_detail"]}
    assert detail == {"tfsa": True, "personal": True, "crypto": False}  # MSB (deposit) isn't listed at all
    assert all_trades(db_session_factory) == []


def test_account_sync_can_be_toggled(client, alice, fake_snaptrade, db_session_factory):
    sync(client, alice)
    crypto = next(a for a in client.get("/brokerage/status", headers=alice).json()["accounts_detail"] if a["account_type"] == "crypto")
    response = client.patch(f"/brokerage/accounts/{crypto['id']}", headers=alice, json={"sync_enabled": True})
    assert response.status_code == 200

    fake_snaptrade.activities["acct-crypto"] = [activity("c1", "ETH", "BUY", 1, 3000, "2026-03-02T15:00:00Z")]
    assert sync(client, alice)["new_trades"] == 1


def test_recent_sync_is_not_repeated_unless_forced(client, alice, fake_snaptrade):
    sync(client, alice, force=True)
    calls_after_first = fake_snaptrade.calls
    assert sync(client, alice, force=False)["skipped_recent_sync"] is True
    assert fake_snaptrade.calls == calls_after_first  # SnapTrade not contacted again


# --- Matching existing trades -----------------------------------------------------------

def test_old_csv_trade_is_taken_over_and_keeps_its_thesis(client, alice, fake_snaptrade, db_session_factory):
    # The old CSV import mislabelled TSX Venture symbols as ".TO" - matching
    # by root symbol still finds it, and the ticker gets corrected.
    add_trade(db_session_factory, user_id=alice_id(db_session_factory), ticker="ZIGY.TO", action="buy",
              quantity=61.3496, price_per_share=1.63, trade_date=date(2026, 3, 3), source="csv",
              thesis_text="Copper demand thesis", conviction_score=4)
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "ZIGY.VN", "BUY", 61.3496, 1.63, "2026-03-03T18:16:35Z")]

    result = sync(client, alice)
    assert result["matched_existing"] == 1 and result["new_trades"] == 0

    [trade] = all_trades(db_session_factory)
    assert trade.external_id == "activity:a1"
    assert trade.source == "snaptrade"
    assert trade.ticker == "ZIGY.V"
    assert trade.thesis_text == "Copper demand thesis"
    assert trade.conviction_score == 4
    assert result["unmatched_csv_trades"] == 0


def test_csv_trade_keeps_its_exact_fx_converted_price(client, alice, fake_snaptrade, db_session_factory):
    # The CSV price used Wealthsimple's exact FX rate; the sync's yfinance
    # rate is only approximate, so the CSV price wins.
    add_trade(db_session_factory, user_id=alice_id(db_session_factory), ticker="NOW", action="buy",
              quantity=1, price_per_share=99.60, trade_date=date(2026, 3, 2), source="csv")
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "NOW", "BUY", 1, 142.38, "2026-03-02T15:00:00Z", security_currency="USD"),
    ]
    sync(client, alice)
    assert float(all_trades(db_session_factory)[0].price_per_share) == pytest.approx(99.60)


def test_manual_trade_is_taken_over_with_broker_price(client, alice, fake_snaptrade, db_session_factory):
    add_trade(db_session_factory, user_id=alice_id(db_session_factory), ticker="VFV.TO", action="buy",
              quantity=10, price_per_share=149.0, trade_date=date(2026, 3, 2), trade_time=time(10, 0),
              source="manual", thesis_text="Core holding", conviction_score=5)
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.25, "2026-03-02T15:00:00Z")]

    sync(client, alice)
    [trade] = all_trades(db_session_factory)
    assert float(trade.price_per_share) == pytest.approx(150.25)
    assert trade.thesis_text == "Core holding"


def test_different_quantity_is_a_different_trade(client, alice, fake_snaptrade, db_session_factory):
    add_trade(db_session_factory, user_id=alice_id(db_session_factory), ticker="VFV.TO", action="buy",
              quantity=3, price_per_share=150.0, trade_date=date(2026, 3, 2), source="csv")
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]

    result = sync(client, alice)
    assert result["new_trades"] == 1
    assert result["unmatched_csv_trades"] == 1
    assert len(all_trades(db_session_factory)) == 2


# --- Real-time orders vs. daily activities --------------------------------------------------

def test_todays_order_appears_before_the_activity_does(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.orders["acct-tfsa"] = [order("o1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z")]
    assert sync(client, alice)["new_trades"] == 1
    [trade] = all_trades(db_session_factory)
    assert trade.external_id == "order:o1"


def test_activity_takes_over_the_order_row_next_day(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.orders["acct-tfsa"] = [order("o1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z")]
    sync(client, alice)

    # The user writes a thesis for the trade in the meantime.
    db = db_session_factory()
    db.query(Trade).one().thesis_text = "Leveraged MU bet"
    db.commit()
    db.close()

    # Next day: the order has aged out, the authoritative activity arrives.
    fake_snaptrade.orders["acct-tfsa"] = []
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z")]
    result = sync(client, alice)

    assert result["new_trades"] == 0 and result["matched_existing"] == 1
    [trade] = all_trades(db_session_factory)
    assert trade.external_id == "activity:a1"
    assert trade.thesis_text == "Leveraged MU bet"


def test_order_and_activity_for_same_trade_in_one_sync(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z")]
    fake_snaptrade.orders["acct-tfsa"] = [order("o1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z")]

    result = sync(client, alice)
    assert result["new_trades"] == 1
    assert len(all_trades(db_session_factory)) == 1


def test_unfilled_orders_are_ignored(client, alice, fake_snaptrade, db_session_factory):
    fake_snaptrade.orders["acct-tfsa"] = [order("o1", "MUU.TO", "BUY", 20, 6.64, "2026-03-05T19:30:50Z", status="PENDING")]
    sync(client, alice)
    assert all_trades(db_session_factory) == []


# --- End to end with holdings ---------------------------------------------------------------

def test_synced_trades_flow_into_holdings(client, alice, fake_snaptrade, prices):
    prices["VFV.TO"] = (160.0, 158.0)
    fake_snaptrade.activities["acct-tfsa"] = [
        activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z"),
        activity("a2", "VFV.TO", "SELL", -4, 155.0, "2026-03-05T15:00:00Z"),
    ]
    sync(client, alice)

    [holding] = client.get("/holdings", headers=alice).json()["holdings"]
    assert holding["ticker"] == "VFV.TO"
    assert holding["shares"] == 6
    assert holding["avg_cost"] == 150


def test_synced_trades_need_a_thesis(client, alice, fake_snaptrade):
    fake_snaptrade.activities["acct-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]
    sync(client, alice)
    assert len(client.get("/trades/incomplete", headers=alice).json()["trades"]) == 1
