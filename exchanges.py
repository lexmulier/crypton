import ccxt

from orders import OrderBook, BestOrderBookAsk, BestOrderBookBid
from utils import handle_bad_requests


class Exchange(object):
    def __init__(self, exchange_id, api_config):
        self.exchange_id = exchange_id
        self.api_config = api_config

        # Initiate CCXT Exchange Class
        self.client = self.initiate_exchange_class()

        # Load all markets in the ExchangeMarket class
        self.markets, self.market_symbols = self.initiate_markets()

        # Load balance for this Exchange
        self.balance = self.get_balance()

    def initiate_exchange_class(self):
        exchange_class = getattr(ccxt, self.exchange_id)
        exchange_api = exchange_class(self.api_config)

        return exchange_api

    @handle_bad_requests()
    def initiate_markets(self):
        markets = self.client.fetch_markets()

        market_symbols = []
        exchange_markets = {}
        for market in markets:
            market_symbol = market['symbol']
            market_symbols.append(market_symbol)
            exchange_markets[market_symbol] = ExchangeMarket(self, market)
        return exchange_markets, market_symbols

    @handle_bad_requests()
    def get_balance(self):
        response = self.client.fetch_balance()
        response_info = response.get("info")

        if isinstance(response_info, list):
            return {}  # Not implemented

        elif isinstance(response_info, dict):
            if response_info.get("data"):
                balance_list = response["info"]["data"]
                return {row['currency']: row for row in balance_list}

        return {}


class ExchangeMarket(object):
    def __init__(self, exchange, market):
        self.exchange = exchange
        self.symbol = market['symbol']
        self.base_coin = market['baseId']
        self.quote_coin = market['quoteId']

        self.info = market

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
    @handle_bad_requests()
    def trading_fees(self):
        try:
            trading_fees = self.exchange.client.fetch_trading_fees(self.symbol)
        except ccxt.NotSupported:
            trading_fees = self.exchange.client.fees.get('trading', {})
        except ValueError:
            trading_fees = self.exchange.client.fees.get('trading', {})
        return trading_fees

    @handle_bad_requests(max_retries=1)
    def get_order_book(self):
        open_orders = self.exchange.client.fetch_order_book(symbol=self.symbol)
        return open_orders["asks"], open_orders["bids"]

    def get_order(self):
        try:
            asks, bids = self.get_order_book()
        except Exception:
            return False, None, None

        if not asks or not bids:
            return False, None, None

        best_ask = BestOrderBookAsk(self, self.exchange, asks)
        best_bid = BestOrderBookBid(self, self.exchange, bids)

        return True, best_ask, best_bid
