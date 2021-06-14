from api.get_client import get_client
from orders import BestOrderBookAsk, BestOrderBookBid
from session import SessionManager
from utils import handle_bad_requests


class Exchange(object):

    _required_config_keys = ["apiKey", "secret"]

    def __init__(self, exchange_id, api_config, preload_market=None, verbose=False):
        self.exchange_id = exchange_id
        self.api_config = api_config
        self.preload_market = preload_market
        self.verbose = verbose

        self.markets = None
        self.market_symbols = None
        self.balance = None

        self.client = get_client(self)
        self.session_manager = SessionManager(self.client)

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

    async def fetch_exchange_specifics(self):
        await self.client.fetch_exchange_specifics()

    async def prepare(self):
        async with self.session_manager:
            await self.fetch_exchange_specifics()
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
        self.base_coin = market.get('base', market.get('baseId'))
        self.quote_coin = market.get('quote', market.get('quoteId'))

        self.info = market
        self.verbose = verbose

        self.trading_fees = None

    async def _retrieve_trading_fees(self):
        self.trading_fees = await self.exchange.client.fetch_fees(self.symbol)

    async def preload(self):
        self.exchange.notify("Preloading market info for {}".format(self.symbol))
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
        async with self.exchange.session_manager:
            try:
                asks, bids = await self.exchange.client.fetch_order_book(symbol=self.symbol, limit=limit)
            except Exception as error:
                self.exchange.notify("Unsuccessful reaching market {}: {}".format(self.symbol, error))
                return False, None, None

        if not asks or not bids:
            self.exchange.notify("No Asks or Bids found for market", self.symbol)
            return False, None, None

        best_ask = BestOrderBookAsk(self,  self.exchange, asks)
        best_bid = BestOrderBookBid(self, self.exchange, bids)

        return True, best_ask, best_bid

    async def sell_order(self, _id, qty, price, params=None):
        return await self._create_order(_id, "sell", qty, price, params=params)

    async def buy_order(self, _id, qty, price, params=None):
        return await self._create_order(_id, "buy", qty, price, params=params)

    async def _create_order(self, _id, side, qty, price, params=None):
        async with self.exchange.session_manager:
            response = await self.exchange.client.create_order(
                _id,
                self.symbol,
                qty,
                price,
                side,
                params=params
            )
            return response
