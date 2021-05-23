import datetime

from bot import Crypton
from config import KRAKEN_CONFIG, KUCOIN_CONFIG, LATOKEN_CONFIG
from models import db


EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    "latoken": LATOKEN_CONFIG,
    #"kucoin": KUCOIN_CONFIG
}


class CryptonExplore(Crypton):

    def __init__(self, *args, **kwargs):
        super(CryptonExplore, self).__init__(*args, **kwargs)
        self.overlapping_markets = self._get_overlapping_markets()

    def _get_overlapping_markets(self):
        market_symbol_lists = [exchange.market_symbols for exchange in self.exchanges.values()]
        return set.intersection(*map(set, market_symbol_lists))

    def _check(self, market_symbols=None):
        for symbol in market_symbols:
            timestamp = datetime.datetime.now()
            for exchange in self.exchanges.values():
                exchange_market = exchange.markets[symbol]
                success, best_ask, best_bid = exchange_market.get_order(limit=1)

                if success is False:
                    self.notify(exchange.exchange_id, "Couldn't reach")
                    continue

                self._insert_prices(exchange_market, best_ask, best_bid, timestamp)

            self.sleep()

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

    def start(self, market_symbols=None, limit=None):
        if market_symbols is None:
            market_symbols = self.overlapping_markets

        count = 0
        while True:
            self.notify("Checking markets...")
            self._check(market_symbols=market_symbols)

            self.sleep(seconds=5)

            if limit == count:
                break

            count += 1


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS, debug=True)
    bot.start()

