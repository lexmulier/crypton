import mock
import pytest

import nest_asyncio

from exchanges import Exchange
from config import EXCHANGES
from tests.testing_api import TestAPI
from trade import CryptonTrade


# We need nested loops in tests only for some reason
nest_asyncio.apply()

EXCHANGES["left"] = {}
EXCHANGES["right"] = {}
MARKET = "ETH/USDT"


# LEFT SIDE IS THE BID EXCHANGE, BASE CURRENCY IS DRIVING
# Asks are always ascending
DEFAULT_LEFT_ASKS = [[10000.0, 10.0]]  # Extra high to ignore this one
# Bids are always descending
DEFAULT_LEFT_BIDS = [
    [1015.0, 10.0],  # There is arbitrage here
    [1014.0, 20.0],  # There is arbitrage here
    [1013.0, 50.0],  # There is arbitrage here
    [1012.0, 10.0],  # There is arbitrage here
    [1011.0, 20.0],  # There is arbitrage here
    [1010.0, 50.0],
    [1009.0, 10.0],
    [1008.0, 20.0],
    [1007.0, 50.0]
]
DEFAULT_LEFT_BALANCE = {
    "ETH": 100000.0
}

# RIGHT SIDE IS THE ASK EXCHANGE, QUOTE CURRENCY IS DRIVING
# Asks are always ascending
DEFAULT_RIGHT_ASKS = [
    [1006.0, 10.0],  # There is arbitrage here
    [1007.0, 20.0],  # There is arbitrage here
    [1008.0, 50.0],  # There is arbitrage here
    [1009.0, 10.0],  # There is arbitrage here
    [1010.0, 20.0],  # There is arbitrage here
    [1011.0, 50.0],
    [1012.0, 10.0],
    [1013.0, 20.0],
    [1014.0, 50.0]
]
# Bids are always descending
DEFAULT_RIGHT_BIDS = [[100.0, 10.0]]  # Extra low to ignore this one
DEFAULT_RIGHT_BALANCE = {
    "USDT": 1000000.0
}


async def prepare_exchanges(
        left_asks=None,
        left_bids=None,
        left_balance=None,
        right_asks=None,
        right_bids=None,
        right_balance=None
):
    left_asks = left_asks or DEFAULT_LEFT_ASKS
    left_bids = left_bids or DEFAULT_LEFT_BIDS
    left_balance = left_balance or DEFAULT_LEFT_BALANCE
    right_asks = right_asks or DEFAULT_RIGHT_ASKS
    right_bids = right_bids or DEFAULT_RIGHT_BIDS
    right_balance = right_balance or DEFAULT_RIGHT_BALANCE

    left_exchange = Exchange("left", preload_market=MARKET, verbose=True)
    left_exchange.client = TestAPI(
        side="left",
        market=MARKET,
        asks=left_asks,
        bids=left_bids,
        balance=left_balance
    )
    await left_exchange.prepare()
    left_exchange.balance = left_balance

    right_exchange = Exchange("right", preload_market=MARKET, verbose=True)
    right_exchange.client = TestAPI(
        side="right",
        market=MARKET,
        asks=right_asks,
        bids=right_bids,
        balance=right_balance
    )
    await right_exchange.prepare()
    right_exchange.balance = right_balance

    exchanges = {"left": left_exchange, "right": right_exchange}

    return exchanges


@pytest.mark.asyncio
@mock.patch('exchanges.get_client')
async def test_base_exchange_balance_is_lowest(_):
    left_balance = {"ETH": 70.0}
    exchanges = await prepare_exchanges(left_balance=left_balance)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    )
    trade.start(simulate=True)

    assert trade.bid.exchange_id == "left"
    assert trade.ask.exchange_id == "right"

    assert trade.bid_base_order_qty == 70.0
    assert round(trade.ask_quote_order_qty, 4) == 70661.0400


@pytest.mark.asyncio
@mock.patch('exchanges.get_client')
async def test_quote_exchange_balance_is_lowest(_):
    right_balance = {"USDT": 75000.0}
    exchanges = await prepare_exchanges(right_balance=right_balance)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    )
    trade.start(simulate=True)

    assert trade.bid.exchange_id == "left"
    assert trade.ask.exchange_id == "right"

    assert round(trade.bid_base_order_qty, 4) == 74.2959
    assert trade.ask_quote_order_qty == 75000.0


@pytest.mark.asyncio
@mock.patch('exchanges.get_client')
async def test_bid_order_book_qty_is_lowest(_):
    left_bids = [
        [1015.0, 10.0],
        [1014.0, 20.0]
    ]
    exchanges = await prepare_exchanges(left_bids=left_bids)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    )
    trade.start(simulate=True)

    assert trade.bid.exchange_id == "left"
    assert trade.ask.exchange_id == "right"

    assert trade.bid_base_order_qty == 30.0
    assert round(trade.ask_quote_order_qty, 4) == 30260.4


@pytest.mark.asyncio
@mock.patch('exchanges.get_client')
async def test_ask_order_book_qty_is_lowest(_):
    right_asks = [
        [1006.0, 10.0],
        [1007.0, 40.0]
    ]
    exchanges = await prepare_exchanges(right_asks=right_asks)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    )
    trade.start(simulate=True)

    assert trade.bid.exchange_id == "left"
    assert trade.ask.exchange_id == "right"

    assert trade.bid_base_order_qty == 50.0
    assert round(trade.ask_quote_order_qty, 4) == 50440.68
