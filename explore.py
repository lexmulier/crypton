import datetime
import itertools
import asyncio

from bot import Crypton
from config import *
from models import db


EXCHANGE_CONFIGS = {
    "liquid": LIQUID_CONFIG,
    "timex": TIMEX_CONFIG,
    "ascendex": ASCENDEX_CONFIG,
    "latoken": LATOKEN_CONFIG,
    "kucoin": KUCOIN_CONFIG,
    "kraken": KRAKEN_CONFIG,
    "binance": BINANCE_CONFIG,
    "dextrade": DEXTRADE_CONFIG
}


class CryptonExplore(Crypton):

    MIN_ARBITRAGE_PERCENTAGE = 1.5

    def __init__(self, exchange_configs, compare_exchange=None, *args, **kwargs):
        super(CryptonExplore, self).__init__(exchange_configs, *args, **kwargs)
        self.compare_to = compare_exchange

    @property
    def exchange_pairs(self):
        pairs = [
            (exchange1, exchange2, set.intersection(*map(set, [exchange1.market_symbols, exchange2.market_symbols])))
            for exchange1, exchange2 in itertools.combinations(self.exchanges.values(), 2)
        ]
        if self.compare_to:
            pairs = [x for x in pairs if x[0].exchange_id == self.compare_to or x[1].exchange_id == self.compare_to]

        return pairs

    def fetch_orders(self, exchange_left, exchange_right, symbol):
        loop = asyncio.get_event_loop()
        tasks = [
            exchange_left.markets[symbol].get_order(),
            exchange_right.markets[symbol].get_order(),
            exchange_left.markets[symbol].retrieve_trading_fees(),
            exchange_right.markets[symbol].retrieve_trading_fees(),
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        success_exchange1, best_ask_exchange1, best_bid_exchange1 = response[0]
        success_exchange2, best_ask_exchange2, best_bid_exchange2 = response[1]

        success = success_exchange1 and success_exchange2
        best_exchange_asks = [best_ask_exchange1, best_ask_exchange2]
        best_exchange_bids = [best_bid_exchange1, best_bid_exchange2]

        return success, best_exchange_asks, best_exchange_bids

    def _check_arbitrage(self, exchange_left, exchange_right, symbol):
        timestamp = datetime.datetime.now()

        success, best_exchange_asks, best_exchange_bids = self.fetch_orders(exchange_left, exchange_right, symbol)
        if not success:
            return

        # TODO: Am I sure that the one with the best asking price and the best bid is always the only arbitrage?
        # Can't there still be arbitrage the other way around?
        best_ask = min(best_exchange_asks)
        best_bid = max(best_exchange_bids)

        # Check if the best ask and best bid are on different exchanges.
        if best_ask.exchange_id == best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return

        # Check if the best asking price with fee is lower than the best asking bid with fee
        margin_percentage = (((best_bid.first_price - best_ask.first_price) / best_ask.first_price) * 100.0)
        if margin_percentage < self.MIN_ARBITRAGE_PERCENTAGE:
            self.notify("Skipping: There is no arbitrage")
            return

        self._insert_arbitrage_opportunity(symbol, best_ask, best_bid, margin_percentage, timestamp)

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
            for exchange_left, exchange_right, overlapping_markets in self.exchange_pairs:
                for symbol in overlapping_markets:
                    self.notify("CHECK {} + {}: {}".format(
                        exchange_left.exchange_id,
                        exchange_right.exchange_id,
                        symbol
                    ))
                    self._check_arbitrage(exchange_left, exchange_right, symbol)


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS, compare_exchange="dextrade", verbose=True)
    bot.start()

