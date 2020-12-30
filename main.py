from time import sleep

from config import KRAKEN_CONFIG, KUCOIN_CONFIG
from exchanges import Exchange

EXCHANGE_CONFIGS = {"kraken": KRAKEN_CONFIG, "kucoin": KUCOIN_CONFIG}


class Crypton(object):

    _sleep_seconds = 1

    def __init__(self, exchange_configs):
        self.exchange_configs = exchange_configs

        self.exchanges = self.initiate_exchanges()

    def initiate_exchanges(self):
        return {
            exchange_id: Exchange(exchange_id, exchange_config)
            for exchange_id, exchange_config in self.exchange_configs.items()
        }

    def fetch_orders(self, market_symbol):
        order_book_list = []
        for exchange in self.exchanges.values():
            print("Checking", exchange.exchange_id)

            exchange_market = exchange.markets[market_symbol]
            success, order = exchange.get_order(exchange_market)

            if success is False:
                print(exchange.exchange_id, "API Failed. We need to retry all Exchanges")
                return False, []

            order_book_list.append(order)

        return True, order_book_list

    def start(self, market_symbol):
        while True:
            success, order_book_list = self.fetch_orders(market_symbol)
            if success is False:
                sleep(self._sleep_seconds)
                continue

            if self.verify_profitability(order_book_list) is False:
                sleep(self._sleep_seconds)
                continue

            self.initiate_order()

    def verify_profitability(self, order_book_list):
        lowest_ask_order = min(order_book_list)
        highest_bid_order = max(order_book_list)
        return True

    def initiate_order(self):
        # WIP
        print('Ordering')


#crypton = Crypton(EXCHANGE_CONFIGS)
#crypton.start("BTC/USDT")
