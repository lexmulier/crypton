from bot import Crypton
from config import KRAKEN_CONFIG, KUCOIN_CONFIG, LATOKEN_CONFIG

EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    #"latoken": LATOKEN_CONFIG,
    "kucoin": KUCOIN_CONFIG
}


class CryptonExplore(Crypton):

    def __init__(self, *args, **kwargs):
        super(CryptonExplore, self).__init__(*args, **kwargs)
        if len(self.exchanges) != 2:
            raise ValueError("Comparison can only be done with exactly 2 exchanges")

        self.overlapping_markets = self.get_overlapping_markets()

    def get_overlapping_markets(self):
        market_symbol_lists = [exchange.market_symbols for exchange in self.exchanges.values()]
        return set.intersection(*map(set, market_symbol_lists))

    def start(self, markets_symbols=None):
        if markets_symbols is None:
            markets_symbols = self.overlapping_markets

        for symbol in markets_symbols:
            for exchange_id, exchange in self.exchanges.items():
                asks, bids = exchange.markets[symbol].get_order_book()

            self.sleep()







if __name__ == "__main__":
    bot = CryptonExplore(EXCHANGE_CONFIGS)

