from config import KRAKEN_CONFIG, KUCOIN_CONFIG
from exchanges import Exchange

EXCHANGE_CONFIGS = {"kraken": KRAKEN_CONFIG, "kucoin": KUCOIN_CONFIG}


class Crypton(object):
    def __init__(self, market_symbol, exchange_configs):
        self.market_symbol = market_symbol
        self.exchange_configs = exchange_configs

    @property
    def exchanges(self):
        return {
            exchange_id: Exchange(exchange_id, exchange_config)
            for exchange_id, exchange_config in self.exchange_configs.items()
        }

    def get_orders(self):
        order_books = []
        for exchange in self.exchanges.values():
            print("Checking", exchange.exchange_id)

            success, order = exchange.get_order(self.market_symbol)
            if success is False:
                print(exchange.exchange_id, "API Failed. We need to retry all Exchanges")
                return False, []

            order_books.append(order)

        return True, order_books

    def start(self):
        while True:
            success, order_books = self.get_orders()
            if success is False:
                continue

            lowest_ask_order = min(order_books)
            highest_bid_order = max(order_books)

            if self.verify_profitability(lowest_ask_order, highest_bid_order) is False:
                print("Order is not profitable")
                continue

            self.initiate_order()

    def verify_profitability(self, lowest_ask_order, highest_bid_order):
        # WIP
        print(lowest_ask_order.ask_price, highest_bid_order.bid_price)
        return True

    def initiate_order(self):
        # WIP
        print('Ordering')


#crypton = Crypton("BTC/USDT", EXCHANGE_CONFIGS)
