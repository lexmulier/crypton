import ccxt

from orders import OrderBook
from utils import handle_bad_requests


class Exchange(object):
    def __init__(self, exchange_id, api_config):
        self.exchange_id = exchange_id
        self.api_config = api_config

        self.client = self.initiate_exchange_class()
        self.markets_info = self.fetch_markets()
        self.market_symbols = self.set_market_symbols()

        self.markets = self.initiate_markets()

    def initiate_exchange_class(self):
        exchange_class = getattr(ccxt, self.exchange_id)
        exchange_api = exchange_class(self.api_config)
        return exchange_api

    @handle_bad_requests()
    def fetch_markets(self):
        return {market["symbol"]: market for market in self.client.fetch_markets()}

    def set_market_symbols(self):
        return list(self.markets_info)

    def initiate_markets(self):
        exchange_markets = {}
        for symbol in self.market_symbols:
            exchange_markets[symbol] = ExchangeMarket(self, symbol)
        return exchange_markets

    @handle_bad_requests()
    def get_balance(self):
        response = self.client.fetch_balance()
        if response["info"]["data"]:
            return response["info"]["data"]
        return {}

    @handle_bad_requests(max_retries=1)
    def get_order_book(self, exchange_market):
        open_orders = self.client.fetch_order_book(symbol=exchange_market.symbol)
        return open_orders["asks"], open_orders["bids"]

    def get_order(self, exchange_market):
        try:
            asks, bids = self.get_order_book(exchange_market)
        except Exception:
            return False, None
        return True, OrderBook(self, exchange_market, asks, bids)


class ExchangeMarket(object):
    def __init__(self, exchange, market_symbol):
        self.exchange = exchange
        self.symbol = market_symbol

        self.info = self.get_market_info()

    def get_market_info(self):
        market_info = self.exchange.markets_info.get(self.symbol)
        if market_info is None:
            raise ValueError(
                "Market {} not found in this exchange {}".format(
                    self.symbol, self.exchange.exchange_id
                )
            )
        return market_info

    @property
    def fee_as_percentage(self):
        return self.info.get("percentage", True) is True

    @property
    def taker(self):
        if self.fee_as_percentage:
            return self.info["taker"] * 100.0
        return self.info["taker"]

    @property
    def maker(self):
        if self.fee_as_percentage:
            return self.info["maker"] * 100.0
        return self.info["maker"]
