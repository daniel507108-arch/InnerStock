# Tests for GET /holdings - the cost-basis (ACB) and gain/loss math.
#
# Every expected number here is worked out by hand in the comments, so a
# failure tells you exactly which part of the math changed. Prices come
# from the fake `prices` fixture as (current_price, previous_close).
from datetime import date, timedelta

import pytest

from conftest import LONG_AGO, log_trade

TODAY = date.today()


def get_holdings(client, headers):
    response = client.get("/holdings", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def holding_for(data, ticker):
    matches = [h for h in data["holdings"] if h["ticker"] == ticker]
    assert matches, f"{ticker} missing from holdings: {data['holdings']}"
    return matches[0]


def test_empty_portfolio(client, alice):
    data = get_holdings(client, alice)
    assert data["holdings"] == []
    assert data["total_value"] == 0
    assert data["position_count"] == 0
    assert data["avg_conviction"] == 0


def test_single_buy(client, alice, prices):
    prices["AAPL"] = (120, 110)
    log_trade(client, alice, "AAPL", "buy", 10, 100)

    data = get_holdings(client, alice)
    aapl = holding_for(data, "AAPL")

    assert aapl["shares"] == 10
    assert aapl["avg_cost"] == 100
    assert aapl["value"] == 1200                     # 10 * 120
    assert aapl["total_gain_loss"] == 200            # (120 - 100) * 10
    assert aapl["total_gain_loss_percent"] == 20     # 20 / 100
    assert aapl["day_gain_loss"] == 100              # held before today: (120 - 110) * 10
    assert aapl["day_gain_loss_percent"] == pytest.approx(9.09)  # 100 / 1100
    assert data["total_value"] == 1200


def test_multiple_buys_average_the_cost(client, alice, prices):
    prices["AAPL"] = (130, 130)
    log_trade(client, alice, "AAPL", "buy", 10, 100)
    log_trade(client, alice, "AAPL", "buy", 10, 140)

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["shares"] == 20
    assert aapl["avg_cost"] == 120                   # (1000 + 1400) / 20
    assert aapl["total_gain_loss"] == 200            # (130 - 120) * 20


def test_partial_sell_keeps_average_cost(client, alice, prices):
    # Moving-average ACB: selling removes shares at the average cost, so the
    # average cost of the shares still held must NOT change.
    prices["AAPL"] = (150, 150)
    log_trade(client, alice, "AAPL", "buy", 10, 100)
    log_trade(client, alice, "AAPL", "buy", 10, 140)
    log_trade(client, alice, "AAPL", "sell", 5, 200)

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["shares"] == 15
    assert aapl["avg_cost"] == 120                   # unchanged by the sell
    assert aapl["total_gain_loss"] == 450            # (150 - 120) * 15


def test_fully_sold_position_is_removed(client, alice, prices):
    prices["AAPL"] = (150, 150)
    prices["MSFT"] = (400, 400)
    log_trade(client, alice, "AAPL", "buy", 10, 100)
    log_trade(client, alice, "AAPL", "sell", 10, 150)
    log_trade(client, alice, "MSFT", "buy", 1, 300)

    data = get_holdings(client, alice)
    assert [h["ticker"] for h in data["holdings"]] == ["MSFT"]
    assert data["position_count"] == 1


def test_rebuy_after_full_exit_starts_fresh_cost_basis(client, alice, prices):
    # The old, fully-sold lot at $100 must not drag down the cost of the
    # new lot bought later at $200.
    prices["AAPL"] = (210, 210)
    log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=LONG_AGO)
    log_trade(client, alice, "AAPL", "sell", 10, 150, trade_date=LONG_AGO + timedelta(days=1))
    log_trade(client, alice, "AAPL", "buy", 5, 200, trade_date=LONG_AGO + timedelta(days=2))

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["shares"] == 5
    assert aapl["avg_cost"] == 200
    assert aapl["total_gain_loss"] == 50             # (210 - 200) * 5


def test_trades_are_processed_in_date_order_not_entry_order(client, alice, prices):
    # Logged out of order: the later-dated rebuy is entered first. If the
    # math followed entry order, the sell would hit the wrong lot.
    prices["AAPL"] = (210, 210)
    log_trade(client, alice, "AAPL", "buy", 5, 200, trade_date=LONG_AGO + timedelta(days=2))
    log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=LONG_AGO)
    log_trade(client, alice, "AAPL", "sell", 10, 150, trade_date=LONG_AGO + timedelta(days=1))

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["shares"] == 5
    assert aapl["avg_cost"] == 200


def test_ticker_case_is_normalized(client, alice, prices):
    prices["AAPL"] = (100, 100)
    log_trade(client, alice, "aapl", "buy", 2, 100)
    log_trade(client, alice, "AAPL", "buy", 3, 100)

    data = get_holdings(client, alice)
    assert data["position_count"] == 1
    assert holding_for(data, "AAPL")["shares"] == 5


def test_shares_bought_today_measure_day_gain_from_purchase_price(client, alice, prices):
    # 10 shares held from before today, 10 more bought today at $115.
    # Old shares: measured from previous close -> 10 * (120 - 110) = 100
    # Today's shares: measured from what was paid -> 10 * (120 - 115) = 50
    prices["AAPL"] = (120, 110)
    log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=LONG_AGO)
    log_trade(client, alice, "AAPL", "buy", 10, 115, trade_date=TODAY)

    data = get_holdings(client, alice)
    aapl = holding_for(data, "AAPL")
    assert aapl["day_gain_loss"] == 150
    # Baseline = 10 * 110 + 10 * 115 = 2250 -> 150 / 2250
    assert aapl["day_gain_loss_percent"] == pytest.approx(6.67)
    assert data["day_change_value"] == 150
    assert data["day_change_percent"] == pytest.approx(6.67)


def test_same_day_sell_comes_out_of_todays_shares_first(client, alice, prices):
    # Bought 5 today then sold 5 today: the sell is assumed to close out
    # today's shares, leaving only the 10 old shares for day gain.
    prices["AAPL"] = (120, 110)
    log_trade(client, alice, "AAPL", "buy", 10, 100, trade_date=LONG_AGO)
    log_trade(client, alice, "AAPL", "buy", 5, 115, trade_date=TODAY)
    log_trade(client, alice, "AAPL", "sell", 5, 118, trade_date=TODAY)

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["shares"] == 10
    assert aapl["day_gain_loss"] == 100              # 10 * (120 - 110)


def test_missing_previous_close_gives_zero_day_change(client, alice, prices):
    # No previous_close yet -> falls back to current price, so day change
    # is 0 instead of a huge fake number.
    prices["AAPL"] = (120, None)
    log_trade(client, alice, "AAPL", "buy", 10, 100)

    aapl = holding_for(get_holdings(client, alice), "AAPL")
    assert aapl["day_gain_loss"] == 0


def test_portfolio_percentages_and_overweight_flag(client, alice, prices):
    prices["AAPL"] = (90, 90)
    prices["MSFT"] = (10, 10)
    log_trade(client, alice, "AAPL", "buy", 10, 90)  # value 900
    log_trade(client, alice, "MSFT", "buy", 10, 10)  # value 100

    data = get_holdings(client, alice)
    aapl = holding_for(data, "AAPL")
    msft = holding_for(data, "MSFT")
    assert aapl["percentage"] == 90
    assert aapl["overweight_flag"] is True           # over 20%
    assert msft["percentage"] == 10
    assert msft["overweight_flag"] is False


def test_avg_conviction_weights_each_position_equally(client, alice, prices):
    # AAPL bought twice (conviction 5 and 1 -> averages to 3), MSFT once (5).
    # Averaged per position first: (3 + 5) / 2 = 4, not (5 + 1 + 5) / 3.
    prices["AAPL"] = (100, 100)
    prices["MSFT"] = (100, 100)
    log_trade(client, alice, "AAPL", "buy", 1, 100, conviction=5)
    log_trade(client, alice, "AAPL", "buy", 1, 100, conviction=1)
    log_trade(client, alice, "MSFT", "buy", 1, 100, conviction=5)

    assert get_holdings(client, alice)["avg_conviction"] == 4


def test_fully_sold_tickers_are_excluded_from_avg_conviction(client, alice, prices):
    prices["AAPL"] = (100, 100)
    prices["MSFT"] = (100, 100)
    log_trade(client, alice, "AAPL", "buy", 1, 100, conviction=1)
    log_trade(client, alice, "AAPL", "sell", 1, 100)
    log_trade(client, alice, "MSFT", "buy", 1, 100, conviction=5)

    assert get_holdings(client, alice)["avg_conviction"] == 5


def test_fractional_shares_fully_sold_leave_no_position(client, alice, prices):
    # Fractional shares are common (Wealthsimple). 0.1 + 0.2 in floating
    # point is 0.30000000000000004, so selling 0.3 must still count as a
    # full exit - not leave a tiny "ghost" position behind.
    prices["AAPL"] = (100, 100)
    log_trade(client, alice, "AAPL", "buy", 0.1, 100)
    log_trade(client, alice, "AAPL", "buy", 0.2, 100)
    log_trade(client, alice, "AAPL", "sell", 0.3, 100)

    data = get_holdings(client, alice)
    assert data["holdings"] == []
    assert data["position_count"] == 0
