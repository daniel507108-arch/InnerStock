# Tests for commercial (developer) SnapTrade keys, where every InnerStock
# user links their OWN brokerage: registration, encrypted secrets, per-user
# isolation, disconnecting, and switching over from a personal key without
# duplicating trades.
import pytest
from cryptography.fernet import Fernet

import secret_box
import snaptrade_sync
from models import BrokerageAccount, SnapTradeUser, Trade, User
from test_snaptrade_sync import FX_RATE, FakeSnapTrade, activity, add_trade, all_trades, sync


@pytest.fixture
def fake(monkeypatch):
    fake = FakeSnapTrade()
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SNAPTRADE_KEY_TYPE", "commercial")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(snaptrade_sync, "get_client", lambda: fake)
    monkeypatch.setattr(snaptrade_sync, "usd_cad_rates", lambda dates: {d: FX_RATE for d in dates})
    return fake


def snaptrade_user_for(db_session_factory, email):
    db = db_session_factory()
    try:
        user = db.query(User).filter(User.email == email).one()
        return db.query(SnapTradeUser).filter(SnapTradeUser.user_id == user.id).first()
    finally:
        db.close()


def connect(client, headers):
    response = client.post("/brokerage/connect", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def give_accounts(fake, db_session_factory, email, accounts):
    """Points the fake's account list for this user's SnapTrade user."""
    fake.accounts[snaptrade_user_for(db_session_factory, email).snaptrade_user_id] = accounts


def tfsa(account_id):
    return {"id": account_id, "kind": "investment", "raw_type": "TFSA", "display_name": "Wealthsimple Trade TFSA"}


# --- Access ------------------------------------------------------------------------

def test_every_user_can_link_their_own_brokerage(client, alice, bob, fake):
    for headers in (alice, bob):
        status = client.get("/brokerage/status", headers=headers).json()
        assert status["available"] is True
        assert status["connected"] is False
        assert status["key_type"] == "commercial"


def test_feature_is_off_without_an_encryption_key(client, alice, fake, monkeypatch):
    # Without a key there's no safe way to store users' SnapTrade secrets.
    monkeypatch.delenv("FIELD_ENCRYPTION_KEY")
    assert client.get("/brokerage/status", headers=alice).json() == {"available": False}
    assert client.post("/brokerage/connect", headers=alice).status_code == 403


# --- Registration --------------------------------------------------------------------

def test_loading_the_dashboard_never_registers_a_snaptrade_user(client, alice, fake, db_session_factory):
    # SnapTrade bills developer keys per user - only "Connect" should register.
    result = sync(client, alice)
    assert result["new_trades"] == 0
    assert fake.registered == {}
    assert fake.calls == 0
    assert snaptrade_user_for(db_session_factory, "alice@example.com") is None


def test_connect_registers_once_and_stores_the_secret_encrypted(client, alice, fake, db_session_factory):
    connect(client, alice)
    connect(client, alice)
    assert len(fake.registered) == 1

    record = snaptrade_user_for(db_session_factory, "alice@example.com")
    real_secret = fake.registered[record.snaptrade_user_id]
    assert record.snaptrade_user_id.startswith("innerstock-")      # random id, not the email
    assert "alice" not in record.snaptrade_user_id
    assert real_secret not in record.user_secret_encrypted            # never stored in plain text
    assert secret_box.decrypt(record.user_secret_encrypted) == real_secret

    # The portal link was requested with Alice's own credentials.
    assert ("login_snap_trade_user", record.snaptrade_user_id, real_secret) in fake.credentials_seen


# --- Isolation -------------------------------------------------------------------------

def test_each_user_only_syncs_their_own_brokerage(client, alice, bob, fake, db_session_factory):
    connect(client, alice)
    connect(client, bob)
    give_accounts(fake, db_session_factory, "alice@example.com", [tfsa("alice-tfsa")])
    give_accounts(fake, db_session_factory, "bob@example.com", [tfsa("bob-tfsa")])
    fake.activities["alice-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]
    fake.activities["bob-tfsa"] = [activity("b1", "XEQT.TO", "BUY", 5, 30.0, "2026-03-02T15:00:00Z")]

    assert sync(client, alice)["new_trades"] == 1
    assert sync(client, bob)["new_trades"] == 1

    assert [t["ticker"] for t in client.get("/trades", headers=alice).json()] == ["VFV.TO"]
    assert [t["ticker"] for t in client.get("/trades", headers=bob).json()] == ["XEQT.TO"]

    # Every data call carried a real user's credentials - none went out bare.
    data_calls = [c for c in fake.credentials_seen if c[0] != "login_snap_trade_user"]
    assert data_calls and all(user_id and secret for _, user_id, secret in data_calls)


def test_one_users_account_id_cannot_be_toggled_by_another(client, alice, bob, fake, db_session_factory):
    connect(client, alice)
    give_accounts(fake, db_session_factory, "alice@example.com", [tfsa("alice-tfsa")])
    sync(client, alice)
    account_id = client.get("/brokerage/status", headers=alice).json()["accounts_detail"][0]["id"]

    response = client.patch(f"/brokerage/accounts/{account_id}", headers=bob, json={"sync_enabled": False})
    assert response.status_code == 404


# --- Disconnecting ------------------------------------------------------------------------

def test_disconnect_removes_snaptrade_user_but_keeps_trades(client, alice, fake, db_session_factory):
    connect(client, alice)
    sid = snaptrade_user_for(db_session_factory, "alice@example.com").snaptrade_user_id
    give_accounts(fake, db_session_factory, "alice@example.com", [tfsa("alice-tfsa")])
    fake.activities["alice-tfsa"] = [activity("a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]
    sync(client, alice)

    response = client.delete("/brokerage/connection", headers=alice)
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert fake.deleted == [sid]
    assert snaptrade_user_for(db_session_factory, "alice@example.com") is None
    assert len(all_trades(db_session_factory)) == 1   # the journal stays

    calls_before = fake.calls
    sync(client, alice)
    assert fake.calls == calls_before   # nothing to sync until they connect again


def test_personal_key_cannot_be_disconnected_from_the_app(client, alice, monkeypatch):
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SNAPTRADE_OWNER_EMAIL", "alice@example.com")
    assert client.delete("/brokerage/connection", headers=alice).status_code == 400


# --- Switching from a personal key / reconnecting ---------------------------------------------

def test_switching_from_personal_key_relinks_trades_without_duplicates(client, alice, fake, monkeypatch, db_session_factory):
    # 1. Personal key: Alice syncs, writes a thesis, and turns PERSONAL off.
    monkeypatch.setenv("SNAPTRADE_KEY_TYPE", "personal")
    monkeypatch.setenv("SNAPTRADE_OWNER_EMAIL", "alice@example.com")
    fake.activities["acct-tfsa"] = [activity("old-a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]
    sync(client, alice)
    personal = next(a for a in client.get("/brokerage/status", headers=alice).json()["accounts_detail"]
                    if a["account_type"] == "personal")
    client.patch(f"/brokerage/accounts/{personal['id']}", headers=alice, json={"sync_enabled": False})
    db = db_session_factory()
    db.query(Trade).one().thesis_text = "Core index holding"
    db.commit()
    db.close()

    # 2. Developer keys: same Wealthsimple accounts come back with NEW ids,
    #    and the same trade with a new activity id.
    monkeypatch.setenv("SNAPTRADE_KEY_TYPE", "commercial")
    connect(client, alice)
    give_accounts(fake, db_session_factory, "alice@example.com", [
        tfsa("new-tfsa"),
        {"id": "new-personal", "kind": "investment", "raw_type": "PERSONAL", "display_name": "Wealthsimple Trade PERSONAL"},
    ])
    fake.activities["new-tfsa"] = [activity("new-a1", "VFV.TO", "BUY", 10, 150.0, "2026-03-02T15:00:00Z")]

    result = sync(client, alice)
    assert result["new_trades"] == 0
    assert result["matched_existing"] == 1

    [trade] = all_trades(db_session_factory)
    assert trade.external_id == "activity:new-a1"
    assert trade.thesis_text == "Core index holding"

    db = db_session_factory()
    new_tfsa = db.query(BrokerageAccount).filter(BrokerageAccount.external_account_id == "new-tfsa").one()
    new_personal = db.query(BrokerageAccount).filter(BrokerageAccount.external_account_id == "new-personal").one()
    old_tfsa = db.query(BrokerageAccount).filter(BrokerageAccount.external_account_id == "acct-tfsa").one()
    db.close()
    assert trade.brokerage_account_id == new_tfsa.id
    assert old_tfsa.disconnected_at is not None
    assert new_personal.sync_enabled is False          # setting carried over by account name

    # Old, disconnected accounts no longer show on the card.
    shown = client.get("/brokerage/status", headers=alice).json()["accounts_detail"]
    assert {a["id"] for a in shown} == {new_tfsa.id, new_personal.id}

    # And a second sync is a no-op.
    assert sync(client, alice)["new_trades"] == 0
    assert len(all_trades(db_session_factory)) == 1
