import datetime
import itertools
import asyncio

from bot import Crypton
from config import *
from models import db


EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    "latoken": LATOKEN_CONFIG,
    "kucoin": KUCOIN_CONFIG,
    "binance": BINANCE_CONFIG
}


class CryptonExplore(Crypton):

    MIN_ARBITRAGE_PERCENTAGE = 1.5

    def __init__(self, *args, **kwargs):
        super(CryptonExplore, self).__init__(*args, **kwargs)

    @property
    def exchange_pairs(self):
        return [
            (exchange1, exchange2, set.intersection(*map(set, [exchange1.market_symbols, exchange2.market_symbols])))
            for exchange1, exchange2 in itertools.combinations(self.exchanges.values(), 2)
        ]

    async def _query_exchange(self, exchange, symbol):
        exchange_market = exchange.markets[symbol]
        success, best_ask, best_bid = exchange_market.get_order()

        if success is False:
            self.notify("CHECK {}: Couldn't reach market {}".format(exchange.exchange_id, symbol))
            return None, None

        return best_ask, best_bid

    async def _check_arbitrage(self, exchange_left, exchange_right, symbol):
        timestamp = datetime.datetime.now()

        left_ask_and_bid = asyncio.create_task(self._query_exchange(exchange_left, symbol))
        right_ask_and_bid = asyncio.create_task(self._query_exchange(exchange_right, symbol))
        await left_ask_and_bid
        await right_ask_and_bid

        left_best_ask, left_best_bid = left_ask_and_bid.result()
        right_best_ask, right_best_bid = right_ask_and_bid.result()

        if any(not x for x in [left_best_ask, left_best_bid, right_best_ask, right_best_bid]):
            return

        # TODO: Am I sure that the one with the best asking price and the best bid is always the only arbitrage?
        # Can't there still be arbitrage the other way around?
        best_ask = min(left_best_ask, right_best_ask)
        best_bid = max(left_best_bid, right_best_bid)

        # Check if the best ask and best bid are on different exchanges.
        if best_ask.exchange_id == best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return

        # Check if the best asking price with fee is lower than the best asking bid with fee
        margin_percentage = (((best_bid.price - best_ask.price) / best_ask.price) * 100.0)
        if (((best_bid.price - best_ask.price) / best_ask.price) * 100.0) < self.MIN_ARBITRAGE_PERCENTAGE:
            self.notify("Skipping: There is no arbitrage")
            return

        self._insert_arbitrage_opportunity(symbol, best_ask, best_bid, margin_percentage, timestamp)

    def _insert_arbitrage_opportunity(self, symbol, ask, bid, margin_percentage, timestamp):
        data = {
            "market": symbol,
            "ask_exchange": ask.exchange.exchange_id,
            "bid_exchange": bid.exchange.exchange_id,
            "arbitrage_margin": margin_percentage,
            "ask_price": ask.price,
            "ask_quantity": ask.quantity,
            "bid_price": bid.price,
            "bid_quantity": bid.quantity,
            "date": timestamp
        }

        self.notify(
            "ARBITRAGE: {} & {} | {} : {}".format(
                data["ask_exchange"],
                data["bid_exchange"],
                symbol,
                margin_percentage
            )
        )

        db.client.arbitrage_opportunity.insert_one(data)

    def start(self):
        while True:
            for exchange_left, exchange_right, overlapping_markets in self.exchange_pairs:
                for symbol in overlapping_markets:
                    self.notify("CHECK {} + {}: {}".format(
                        exchange_left.exchange_id,
                        exchange_right.exchange_id,
                        symbol
                    ))
                    asyncio.run(self._check_arbitrage(exchange_left, exchange_right, symbol))


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS, verbose=True)
    bot.start()

