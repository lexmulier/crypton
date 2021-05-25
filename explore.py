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
        success, best_ask, best_bid = exchange_market.get_order(limit=1)

        if success is False:
            self.notify("CHECK {}: Couldn't reach market {}".format(exchange.exchange_id, symbol))
            return None, None

        return best_ask, best_bid

    async def _check_arbitrage(self, exchange_left, exchange_right, symbol):
        left_ask_and_bid = asyncio.create_task(self._query_exchange(exchange_left, symbol))
        right_ask_and_bid = asyncio.create_task(self._query_exchange(exchange_right, symbol))
        await left_ask_and_bid
        await right_ask_and_bid
        self.notify('Got both!')


        return

        # for symbol in market_symbols:
        #     timestamp = datetime.datetime.now()
        #     for exchange in self.exchanges.values():
        #         exchange_market = exchange.markets[symbol]
        #         success, best_ask, best_bid = exchange_market.get_order(limit=1)
        #
        #         if success is False:
        #             self.notify(exchange.exchange_id, "Couldn't reach")
        #             continue
        #
        #         self._insert_prices(exchange_market, best_ask, best_bid, timestamp)
        #
        #     self.sleep()

    def _insert_prices(self, market, ask, bid, timestamp):
        data = {
            "market": market.symbol,
            "exchange": market.exchange.exchange_id,
            "ask": ask.price,
            "bid": bid.price,
        }

        self.notify("{} on {} | ask {} - bid {}".format(*data.values()))

        data["date"] = timestamp
        db.client.explore.insert_one(data)

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
            break  # For now


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS, verbose=True)
    bot.start()

