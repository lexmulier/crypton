import datetime
import asyncio
import itertools

from config import *
from exchanges import initiate_exchanges
from models import db


class CryptonExplore(object):

    MIN_ARBITRAGE_PERCENTAGE = 1.5

    def __init__(self, exchange_ids, verbose=True):
        self.exchanges = initiate_exchanges(exchange_ids, verbose=verbose)
        self.verbose = verbose

    @property
    def markets(self):
        return set([market for exchange in self.exchanges.values() for market in exchange.market_symbols])

    def notify(self, *args):
        if self.verbose:
            print(*args)

    @staticmethod
    def _fetch_orders(exchanges, market):
        loop = asyncio.get_event_loop()
        tasks = [exchange.markets[market].get_orders() for exchange in exchanges]
        return loop.run_until_complete(asyncio.gather(*tasks))

    def fetch_orders(self, exchanges, market):
        response = self._fetch_orders(exchanges, market)
        results = [x for x in response if x[0]]

        for left_order, right_order in itertools.combinations(results, 2):
            yield [left_order[1], right_order[1]], [left_order[2], right_order[2]]

    def _check_arbitrage(self, exchanges, market):
        timestamp = datetime.datetime.now()

        for best_exchange_asks, best_exchange_bids in self.fetch_orders(exchanges, market):
            best_ask = min(best_exchange_asks, key=lambda x: x.first_price)
            best_bid = max(best_exchange_bids, key=lambda x: x.first_price)

            # Check if the best ask and best bid are on different exchanges.
            if best_ask.exchange_id == best_bid.exchange_id:
                self.notify("Skipping: Best ask and best bid are on the same exchange")
                continue

            # Check if the best asking price with fee is lower than the best asking bid with fee
            margin_percentage = (((best_bid.first_price - best_ask.first_price) / best_ask.first_price) * 100.0)
            if margin_percentage < self.MIN_ARBITRAGE_PERCENTAGE:
                self.notify("Skipping: There is no arbitrage")
                continue

            self._insert_arbitrage_opportunity(market, best_ask, best_bid, margin_percentage, timestamp)

    def _insert_arbitrage_opportunity(self, symbol, ask, bid, margin_percentage, timestamp):
        data = {
            "market": symbol,
            "ask_exchange": ask.exchange.exchange_id,
            "bid_exchange": bid.exchange.exchange_id,
            "arbitrage_margin": margin_percentage,
            "ask_price": ask.first_price,
            "ask_quantity": ask.first_quantity,
            "bid_price": bid.first_price,
            "bid_quantity": bid.first_quantity,
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
            for market in self.markets:
                exchanges = [x for x in self.exchanges.values() if x.markets.get(market)]
                if len(exchanges) > 1:
                    self.notify("CHECK {}: {}".format(" + ".join([x.exchange_id for x in exchanges]), market))
                    self._check_arbitrage(exchanges, market)


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGES.keys())
    bot.start()

