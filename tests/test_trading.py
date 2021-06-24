import mock
import pytest

import nest_asyncio
import mongomock

from exchanges import Exchange
from config import EXCHANGES
from tests.mock_api import MockAPI
from trade import CryptonTrade


# We need nested loops in tests only for some reason
nest_asyncio.apply()

EXCHANGES["left"] = {}
EXCHANGES["right"] = {}
MARKET = "ETH/USDT"


async def prepare_exchanges(left_asks, left_bids, left_balance, right_asks, right_bids, right_balance):
    left_exchange = Exchange("left", preload_market=MARKET, verbose=True)
    left_exchange.client = MockAPI(
        side="left",
        market=MARKET,
        asks=left_asks,
        bids=left_bids,
        balance=left_balance
    )
    await left_exchange.prepare()
    left_exchange.balance = left_balance

    right_exchange = Exchange("right", preload_market=MARKET, verbose=True)
    right_exchange.client = MockAPI(
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
async def test_profit_calculation(_):
    # LEFT
    # Asks are always ascending
    left_asks = [
        [10000.0, 10.0],
    ]
    # Bids are always descending
    left_bids = [
        [1015.0, 10.0],
        [1014.0, 20.0],
        [1013.0, 50.0],
        [1012.0, 10.0],
        [1011.0, 20.0],
        [1010.0, 50.0],
        [1009.0, 10.0],
        [1008.0, 20.0],
        [1007.0, 50.0]
    ]
    left_balance = {
        "ETH": 170.0
    }

    # RIGHT
    # Asks are always ascending
    right_asks = [
        [1006.0, 10.0],
        [1007.0, 220.0],
        [1008.0, 50.0],
        [1009.0, 10.0],
        [1010.0, 20.0],
        [1011.0, 50.0],
        [1012.0, 10.0],
        [1013.0, 20.0],
        [1014.0, 50.0]
    ]
    # Bids are always descending
    right_bids = [
        [100.0, 10.0],
    ]
    right_balance = {
        "USDT": 180000.0
    }

    exchanges = await prepare_exchanges(left_asks, left_bids, left_balance, right_asks, right_bids, right_balance)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    ).start()




    assert False





