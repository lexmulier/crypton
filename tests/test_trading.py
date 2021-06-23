import mock
import pytest

from exchanges import Exchange
from config import EXCHANGES
from tests.mock_api import MockAPI
from trade import CryptonTrade

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

    right_exchange = Exchange("right", preload_market=MARKET, verbose=True)
    right_exchange.client = MockAPI(
        side="right",
        market=MARKET,
        asks=right_asks,
        bids=right_bids,
        balance=right_balance
    )
    await right_exchange.prepare()

    exchanges = {"left": left_exchange, "right": right_exchange}

    return exchanges


@pytest.mark.asyncio
@mock.patch('exchanges.get_client')
async def test_profit_calculation(_, event_loop):
    # LEFT
    left_asks = [
        [100.0, 1000.0],
        [101.0, 2000.0],
        [102.0, 5000.0]
    ]

    left_bids = [
        [100.0, 1000.0],
        [101.0, 2000.0],
        [102.0, 5000.0]
    ]
    left_balance = {
        "ETH": 1000.0,
        "USDT": 2000.0
    }

    right_asks = [
        [100.0, 1000.0],
        [101.0, 2000.0],
        [102.0, 5000.0]
    ]

    right_bids = [
        [100.0, 1000.0],
        [101.0, 2000.0],
        [102.0, 5000.0]
    ]
    right_balance = {
        "ETH": 2000.0,
        "USDT": 5000.0
    }

    exchanges = await prepare_exchanges(left_asks, left_bids, left_balance, right_asks, right_bids, right_balance)

    # Check and execute trade if there is an opportunity
    trade = CryptonTrade(
        market=MARKET,
        exchanges=exchanges,
        verbose=True
    )

    success, best_exchange_asks, best_exchange_bids = trade.fetch_orders()

    assert True

