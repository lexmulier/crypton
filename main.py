from time import sleep

from config import KRAKEN_CONFIG, KUCOIN_CONFIG
from exchanges import Exchange

EXCHANGE_CONFIGS = {"kraken": KRAKEN_CONFIG, "kucoin": KUCOIN_CONFIG}


class Crypton(object):

    _sleep_seconds = 1

    DEFAULT_MIN_PROFIT_MARGIN = 0.5

    def __init__(self, exchange_configs, profit_margin=None):
        self.exchange_configs = exchange_configs

        if profit_margin is not None:
            self.minimal_profit_margin = profit_margin
        else:
            self.minimal_profit_margin = self.DEFAULT_MIN_PROFIT_MARGIN

        self.exchanges = self.initiate_exchanges()

    def initiate_exchanges(self):
        return {
            exchange_id: Exchange(exchange_id, exchange_config)
            for exchange_id, exchange_config in self.exchange_configs.items()
        }

    def fetch_orders(self, market_symbol):
        order_book_list = []
        for exchange in self.exchanges.values():
            print("Pinging", exchange.exchange_id)

            exchange_market = exchange.markets[market_symbol]
            success, order = exchange_market.get_order()

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

            if self.check_profit(order_book_list) is False:
                sleep(self._sleep_seconds)
                continue

            self.initiate_order()

            # For now we break
            break

    def check_profit(self, order_book_list):
        lowest_selling_order = min(order_book_list)
        highest_buying_order = max(order_book_list)

        if lowest_selling_order == highest_buying_order:
            return False

        profit_margin = lowest_selling_order.ask_price_with_fee / highest_buying_order.bid_price_with_fee
        if self.minimal_profit_margin > profit_margin:
            return False

        print('Lowest ask (with fee): {} ({})'.format(lowest_selling_order.bid_price, lowest_selling_order.bid_price_with_fee))
        print('Highest bid (with fee): {} ({})'.format(highest_buying_order.bid_price, highest_buying_order.bid_price_with_fee))
        print('Profit margin {}'.format(profit_margin))

        return True

    def initiate_order(self):
        # WIP
        print('Ordering')


#crypton = Crypton(EXCHANGE_CONFIGS)
#crypton.start("BTC/USDT")
