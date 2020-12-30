import ccxt

from orders import OrderBook
from utils import handle_bad_requests


class Exchange(object):
    def __init__(self, exchange_id, api_config):
        self.exchange_id = exchange_id
        self.api_config = api_config

        self.client = self.initiate_exchange_class()
        self.market_info = self.load_markets()
        self.market_symbols = self.load_market_symbols()

    def initiate_exchange_class(self):
        exchange_class = getattr(ccxt, self.exchange_id)
        exchange_api = exchange_class(self.api_config)
        return exchange_api

    @handle_bad_requests()
    def load_markets(self):
        return self.client.load_markets()

    def load_market_symbols(self):
        return list(self.market_info.keys())

    def get_market_info(self, market_symbol):
        market_info = self.market_info.get(market_symbol)
        if market_info is None:
            raise ValueError(
                "Market {} not found in this exchange {}".format(
                    market_symbol, self.exchange_id
                )
            )
        return market_info

    @handle_bad_requests()
    def get_balance(self):
        response = self.client.fetch_balance()
        if response["info"]["data"]:
            return response["info"]["data"]
        return {}

    @handle_bad_requests(max_retries=1)
    def get_order_book(self, market_symbol):
        open_orders = self.client.fetch_order_book(symbol=market_symbol)
        return open_orders["asks"], open_orders["bids"]

    def get_order(self, market_symbol):
        try:
            asks, bids = self.get_order_book(market_symbol)
        except Exception:
            return False, None
        return True, OrderBook(self, market_symbol, asks, bids)
