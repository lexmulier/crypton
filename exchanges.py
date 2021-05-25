import ccxt

from orders import BestOrderBookAsk, BestOrderBookBid
from utils import handle_bad_requests


class Exchange(object):

    _required_config_keys = ["apiKey", "secret"]

    def __init__(self, exchange_id, api_config, verbose=False):
        self.exchange_id = exchange_id
        self.api_config = api_config
        self.verbose = verbose

        if any([key not in self.api_config for key in self._required_config_keys]):
            raise ValueError("Exchange configuration missing required input parameters")

        # Initiate CCXT Exchange Class
        self.client = self.initiate_exchange_class()

        # Load all markets in the ExchangeMarket class
        self.markets, self.market_symbols = self.initiate_markets()

        # Load balance for this Exchange
        self.balance = self.retrieve_exchange_balances()

    def notify(self, *args):
        if self.verbose:
            print("EXCHANGE {}:".format(self.exchange_id), *args)

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
            exchange_markets[market_symbol] = ExchangeMarket(self, market, verbose=self.verbose)

        self.notify("Found {} markets".format(len(exchange_markets)))

        return exchange_markets, market_symbols

    def get_balance(self, symbol):
        return self.balance.get(symbol, 0.0)

    def get_balance_fake(self, symbol):
        # TODO: REMOVE!!
        from random import randrange
        return randrange(1, 500)

    @handle_bad_requests()
    def retrieve_exchange_balances(self):
        response = self.client.fetch_balance()
        balance_data = response.get("info")

        balance = dict()
        if isinstance(balance_data, list):
            pass

        elif isinstance(balance_data, dict):
            balance = {row["asset"]: float(row["free"]) for row in balance_data.get("balances", {})}

        return balance


class ExchangeMarket(object):
    def __init__(self, exchange, market, verbose=False):
        self.exchange = exchange
        self.symbol = market['symbol']
        self.base_coin = market['baseId']
        self.quote_coin = market['quoteId']

        self.info = market
        self.verbose = verbose

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
        except (ccxt.NotSupported, ValueError):
            trading_fees = self.exchange.client.fees.get('trading', {})
        return trading_fees

    @handle_bad_requests(max_retries=1)
    def get_order_book(self, limit=None):
        open_orders = self.exchange.client.fetch_order_book(symbol=self.symbol, limit=limit)
        return open_orders["asks"], open_orders["bids"]

    def get_order_book_fake(self, limit=None):
        # TODO: REMOVE!!
        from random import randrange
        variance = len(self.exchange.exchange_id)
        asks = [[1000 + (10 * variance) + x + 2, randrange(1, 500)] for x in range(1, 50)]
        bids = [[1000 + (10 * variance) + x, randrange(1, 500)] for x in range(1, 50)]
        return asks, bids

    def get_order(self, limit=None):
        try:
            asks, bids = self.get_order_book(limit=limit)
        except Exception as error:
            self.exchange.notify("Unsuccessful reaching market {}: {}".format(self.symbol, error))
            return False, None, None

        if not asks or not bids:
            self.exchange.notify("No Asks or Bids found for market", self.symbol)
            return False, None, None

        best_ask = BestOrderBookAsk(self, self.exchange, asks)
        best_bid = BestOrderBookBid(self, self.exchange, bids)

        return True, best_ask, best_bid
