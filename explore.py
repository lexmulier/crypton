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
            for exchange_id, exchange in self.exchanges.items():
                try:
                    asks, bids = exchange.markets[symbol].get_order_book(limit=1)
                except Exception as error:
                    if self.debug:
                        print("{} - {}: {}".format(exchange_id, symbol, error))
                    continue

                if not asks or not bids:
                    continue

                self._insert_prices(exchange_id, symbol, asks, bids)

            self.sleep()

    def _insert_prices(self, exchange_id, symbol, asks, bids):
        data = {
            "market": symbol,
            "exchange": exchange_id,
            "ask": asks[0][0],
            "bid": bids[0][0],
        }

        if self.debug:
            print("{} on {} | ask {} - bid {}".format(*data.values()))

        data["date"] = datetime.datetime.now()
        db.client.explore.insert_one(data)

    def start(self, market_symbols=None, limit=None):
        if market_symbols is None:
            market_symbols = self.overlapping_markets

        count = 0
        while True:
            print("Checking markets...")
            self._check(market_symbols=market_symbols)

            self.sleep(seconds=5)

            if limit == count:
                break

            count += 1


if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS, debug=True)
    bot.start()

