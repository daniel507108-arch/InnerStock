# Tests for POST /trades/import/wealthsimple - turning a Wealthsimple
# activity export into trades. Uses small inline CSVs in the same column
# layout as the real export.
import pytest

HEADER = "activity_type,activity_sub_type,symbol,quantity,unit_price,description,effective_at\n"


def import_csv(client, headers, rows):
    response = client.post(
        "/trades/import/wealthsimple",
        headers=headers,
        files={"file": ("export.csv", HEADER + "".join(rows), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def imported_trades(client, headers):
    return {t["ticker"]: t for t in client.get("/trades", headers=headers).json()}


def test_cad_native_symbol_gets_tsx_suffix(client, alice):
    # No "FX Rate" in the description means a CAD-priced security, so a
    # bare symbol is treated as the TSX listing.
    import_csv(client, alice, ["Trade,BUY,VFV,10,150.00,Vanguard S&P 500,2026-03-02T10:00:00-05:00\n"])

    trades = imported_trades(client, alice)
    assert list(trades) == ["VFV.TO"]
    assert float(trades["VFV.TO"]["price_per_share"]) == 150.00


def test_us_stock_price_is_converted_back_to_usd(client, alice):
    # Wealthsimple reports the price already converted to CAD. Dividing by
    # the FX rate puts it back in USD, matching what yfinance returns.
    import_csv(client, alice, ["Trade,BUY,AAPL,2,250.00,Apple Inc. FX Rate: 1.25,2026-03-02T10:00:00-05:00\n"])

    trades = imported_trades(client, alice)
    assert list(trades) == ["AAPL"]                  # no .TO suffix
    assert float(trades["AAPL"]["price_per_share"]) == pytest.approx(200.00)


def test_already_suffixed_symbol_is_left_alone(client, alice):
    import_csv(client, alice, ["Trade,BUY,HUT.TO,4,20.00,Hut 8,2026-03-02T10:00:00-05:00\n"])
    assert list(imported_trades(client, alice)) == ["HUT.TO"]


def test_sell_quantity_sign_is_dropped(client, alice):
    # Wealthsimple exports sells with a negative quantity.
    import_csv(client, alice, ["Trade,SELL,VFV,-3,155.00,Vanguard S&P 500,2026-03-05T10:00:00-05:00\n"])

    trade = imported_trades(client, alice)["VFV.TO"]
    assert trade["action"] == "sell"
    assert float(trade["quantity"]) == 3


def test_non_trade_rows_are_skipped(client, alice):
    result = import_csv(client, alice, [
        "Deposit,,,,,e-Transfer,2026-03-01T10:00:00-05:00\n",
        "Dividend,,VFV,,,Dividend payment,2026-03-01T10:00:00-05:00\n",
        "Trade,BUY,VFV,1,150.00,Vanguard S&P 500,2026-03-02T10:00:00-05:00\n",
    ])
    assert result["successful_count"] == 1
    assert result["skipped_count"] == 2
    assert result["errors"] == []


def test_bad_rows_are_reported_without_blocking_good_rows(client, alice):
    result = import_csv(client, alice, [
        "Trade,BUY,VFV,1,150.00,Vanguard S&P 500,2026-03-02T10:00:00-05:00\n",
        "Trade,BUY,VFV,abc,150.00,Vanguard S&P 500,2026-03-02T10:00:00-05:00\n",
        "Trade,BUY,,1,150.00,No symbol,2026-03-02T10:00:00-05:00\n",
        "Trade,BUY,VFV,1,150.00,Vanguard S&P 500,not-a-date\n",
    ])
    assert result["successful_count"] == 1
    assert [e["row"] for e in result["errors"]] == [2, 3, 4]


def test_trade_date_is_taken_from_timestamp(client, alice):
    import_csv(client, alice, ["Trade,BUY,VFV,1,150.00,Vanguard S&P 500,2026-04-15T12:03:38-04:00\n"])
    assert imported_trades(client, alice)["VFV.TO"]["trade_date"] == "2026-04-15"


def test_imported_trades_need_a_thesis(client, alice):
    # Imports have no thesis, so they land in the "incomplete" backlog.
    import_csv(client, alice, ["Trade,BUY,VFV,1,150.00,Vanguard S&P 500,2026-03-02T10:00:00-05:00\n"])

    incomplete = client.get("/trades/incomplete", headers=alice).json()["trades"]
    assert len(incomplete) == 1
    assert incomplete[0]["thesis_text"] is None
