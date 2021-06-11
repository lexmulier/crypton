import asyncio

from orders import BestOrderBookAsk, BestOrderBookBid
from session import SessionManager
from utils import handle_bad_requests
from api import get_client


class Exchange(object):

    _required_config_keys = ["apiKey", "secret"]
    client = None

    def __init__(self, exchange_id, api_config, preload_market=None, verbose=False):
        self.exchange_id = exchange_id
        self.api_config = api_config
        self.preload_market = preload_market
        self.verbose = verbose

        if any([key not in self.api_config for key in self._required_config_keys]):
            raise ValueError("Exchange configuration missing required input parameters")

        self.markets = None
        self.market_symbols = None
        self.balance = None

    def notify(self, *args):
        if self.verbose:
            print("EXCHANGE {}:".format(self.exchange_id), *args)

    #@handle_bad_requests()
    async def retrieve_balance(self):
        self.balance = await self.client.fetch_balance()

    #@handle_bad_requests()
    async def initiate_markets(self):
        markets = await self.client.fetch_markets()

        market_symbols = []
        exchange_markets = {}
        for market in markets:
            market_symbol = market['symbol']
            market_symbols.append(market_symbol)
            exchange_markets[market_symbol] = ExchangeMarket(
                self,
                market,
                verbose=self.verbose
            )

        self.notify("Found {} markets".format(len(exchange_markets)))

        self.markets = exchange_markets
        self.market_symbols = market_symbols

    async def prepare(self):
        async with SessionManager(self):
            await self.initiate_markets()
            await self.retrieve_balance()

            if self.preload_market:
                await self.markets[self.preload_market].preload()

    def get_balance(self, symbol):
        return self.balance.get(symbol, 0.0)


class ExchangeMarket(object):
    def __init__(self, exchange, market, verbose=False):
        self.exchange = exchange
        self.symbol = market['symbol']
        self.base_coin = market['baseId']
        self.quote_coin = market['quoteId']

        self.info = market
        self.verbose = verbose

        self.trading_fees = None

    #@handle_bad_requests()
    async def _retrieve_trading_fees(self):
        self.trading_fees = await self.exchange.client.fetch_fees(self.symbol)
        self.exchange.notify("Preparing market {} by preloading specific info".format(self.symbol))

    async def preload(self):
        await self._retrieve_trading_fees()

    def get_market_info(self):
        market_info = self.exchange.markets_info.get(self.symbol)
        if market_info is None:
            raise ValueError(
                "Market {} not found in this exchange {}".format(
                    self.symbol, self.exchange.exchange_id
                )
            )
        return market_info

    #@handle_bad_requests(max_retries=1)
    async def get_order(self, limit=None):
        async with SessionManager(self.exchange):
            try:
                asks, bids = await self.exchange.client.fetch_order_book(symbol=self.symbol, limit=limit)
            except Exception as error:
                self.exchange.notify("Unsuccessful reaching market {}: {}".format(self.symbol, error))
                return False, None, None

        if not asks or not bids:
            self.exchange.notify("No Asks or Bids found for market", self.symbol)
            return False, None, None

        best_ask = BestOrderBookAsk(self, self.exchange, asks)
        best_bid = BestOrderBookBid(self, self.exchange, bids)

        return True, best_ask, best_bid
