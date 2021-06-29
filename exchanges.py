import asyncio
import logging
import datetime

from api.get_client import get_client
from config import EXCHANGES
from log import CryptonLogger
from models import db
from orders import BestOrderAsk, BestOrderBid
from session import SessionManager

logger = logging.getLogger(__name__)


class Exchange(object):

    def __init__(self,
                 exchange_id,
                 preload_market=None,
                 layered_quote_qty_calc=True,
                 min_profit_perc=None,
                 min_profit_amount=None,
                 log_level=False,
                 ):

        if exchange_id not in EXCHANGES:
            raise ValueError(f"Exchange {self.exchange_id} does not exist according to configuration!")

        self.exchange_id = exchange_id
        self.api_config = EXCHANGES[exchange_id]
        self.preload_market = preload_market

        self.min_profit_perc = min_profit_perc
        self.min_profit_amount = min_profit_amount
        self.layered_quote_qty_calc = layered_quote_qty_calc

        self.markets = None
        self.market_symbols = None
        self.balance = {}

        self.client = get_client(self)
        self.session_manager = SessionManager(self.client)

        if log_level is not None:
            CryptonLogger(level=log_level).initiate()

        exchange_logger = {'module_fields': f"EXCHANGE {self.exchange_id}"}
        self.log = logging.LoggerAdapter(logger, exchange_logger)

    async def _initiate_markets(self):
        markets = await self.client.fetch_markets()

        market_symbols = []
        exchange_markets = {}
        for market in markets:
            market_symbol = market['symbol']
            market_symbols.append(market_symbol)
            exchange_markets[market_symbol] = ExchangeMarket(self, market)

        self.log.info(f"Found {len(exchange_markets)} markets")

        self.markets = exchange_markets
        self.market_symbols = market_symbols

    async def _fetch_exchange_specifics(self):
        await self.client.fetch_exchange_specifics()

    async def prepare(self):
        async with self.session_manager:
            await self._fetch_exchange_specifics()
            await self._initiate_markets()
            await self._retrieve_balance()

            if self.preload_market:
                await self.markets[self.preload_market].preload()

    def get_balance(self, symbol=None, from_database=False):
        if from_database or not self.balance:
            balance = db.client.balance_current.find_one({"exchange": self.exchange_id}, {"balance": True})
            self.balance.update(balance["balance"])
        return self.balance.get(symbol, 0.0)

    async def _retrieve_balance(self):
        balance = await self.client.fetch_balance()
        if balance:
            db.client.balance_current.update_one(
                {"exchange": self.exchange_id},
                {"$set": {f"balance.{coin}": available for coin, available in balance.items()}},
                upsert=True
            )
            timestamp = datetime.datetime.now()
            history = [
                {"balance": available, "coin": coin, "exchange": self.exchange_id, "timestamp": timestamp}
                for coin, available in balance.items()
            ]
            db.client.balance_history.insert_many(history)
        self.balance.update(balance)

    async def retrieve_balance(self):
        async with self.session_manager:
            await self._retrieve_balance()


class ExchangeMarket(object):

    _default_min_base_qty = 0.0
    _default_min_quote_qty = 0.0

    _default_base_precision = 8
    _default_quote_precision = 8
    _default_price_precision = 8

    def __init__(self, exchange, market):
        self.exchange = exchange
        self.symbol = market['symbol']
        self.base_coin = market.get('base', market.get('baseId'))
        self.quote_coin = market.get('quote', market.get('quoteId'))
        self.min_base_qty = market.get('min_base_qty', self._default_min_base_qty)
        self.min_quote_qty = market.get('min_quote_qty', self._default_min_quote_qty)
        self.base_precision = market.get('base_precision', self._default_base_precision)
        self.quote_precision = market.get('quote_precision', self._default_quote_precision)
        self.price_precision = market.get('price_precision', self._default_price_precision)
        self.info = market

        self.trading_fees = None

    async def _retrieve_trading_fees(self):
        self.trading_fees = await self.exchange.client.fetch_fees(self.symbol)

    async def preload(self):
        self.exchange.log.info(f"Preloading market info for {self.symbol}")
        await self._retrieve_trading_fees()

    def get_market_info(self):
        market_info = self.exchange.markets_info.get(self.symbol)
        if market_info is None:
            raise ValueError(f"Market {self.symbol} not found in this exchange {self.exchange.exchange_id}")
        return market_info

    async def get_orders(self, limit=None):
        async with self.exchange.session_manager:
            try:
                asks, bids = await self.exchange.client.fetch_order_book(symbol=self.symbol, limit=limit)
            except Exception as error:
                self.exchange.log.info(f"Unsuccessful reaching market {self.symbol}: {error}")
                return False, None, None

        if not asks or not bids:
            self.exchange.log.info(f"No Asks or Bids found for market {self.symbol}")
            return False, None, None

        best_ask = BestOrderAsk(self, self.exchange, asks)
        best_bid = BestOrderBid(self, self.exchange, bids)

        return True, best_ask, best_bid


def initiate_exchanges(exchange_ids, preload_market=None, exchange_settings=None):
    exchange_settings = exchange_settings or {}

    # Initiate exchanges
    exchanges = {}
    for exchange_id in exchange_ids:
        exchange = Exchange(
            exchange_id,
            preload_market=preload_market,
            **exchange_settings.get(exchange_id, {})
        )
        exchanges[exchange_id] = exchange

    # Prepare exchanges
    loop = asyncio.get_event_loop()
    tasks = [exchange.prepare() for exchange in exchanges.values()]
    loop.run_until_complete(asyncio.gather(*tasks))

    return exchanges
