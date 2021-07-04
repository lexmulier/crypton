import logging

from ccxt import async_support as ccxt

from api.base import BaseAPI

logging.getLogger("ccxt").setLevel(logging.CRITICAL)


class CcxtAPI(BaseAPI):
    def __init__(self, *args, exchange_id=None, **kwargs):
        super(CcxtAPI, self).__init__(*args, **kwargs)

        if self.exchange:
            self.exchange_id = self.exchange.exchange_id
        else:
            self.exchange_id = exchange_id

        self.session = None

    @property
    def client(self):
        exchange_class = getattr(ccxt, self.exchange_id)
        self.config["session"] = self.session
        exchange = exchange_class(self.config)
        return exchange

    async def fetch_fees(self, market):
        try:
            response = await self.client.fetch_trading_fee(market)
        except (ccxt.NotSupported, ValueError):
            response = self.client.fees.get('trading', {})

        if 'maker' not in response or 'taker' not in response:
            raise ValueError("API is different than expected: no maker or taker fees")

        return response

    async def fetch_markets(self):
        response = await self.client.fetch_markets()
        return response

    async def fetch_balance(self):
        response = await self.client.fetch_balance()

        balance_data = response.get("info")

        balance = dict()
        if isinstance(balance_data, list):
            pass

        elif isinstance(balance_data, dict):
            balance = {row["asset"]: float(row["free"]) for row in balance_data.get("balances", {})}

        return balance

    async def fetch_order_book(self, symbol, limit=None):
        response = await self.client.fetch_order_book(symbol=symbol, limit=limit)
        return response["asks"], response["bids"]

    async def create_order(self, symbol, order_type, side, qty, price, params=None):
        params = params if params else {}
        response = await self.client.create_order(symbol, order_type, side, qty, price, params)
        return response

    async def close(self):
        await self.client.close()
