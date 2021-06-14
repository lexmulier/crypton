import logging

from ccxt import async_support as ccxt

logging.getLogger("ccxt").setLevel(logging.CRITICAL)


class CcxtAPI(object):
    def __init__(self, exchange):
        self.exchange = exchange
        self.session = None

    @property
    def client(self):
        exchange_class = getattr(ccxt, self.exchange.exchange_id)
        self.exchange.api_config["session"] = self.session
        exchange = exchange_class(self.exchange.api_config)
        return exchange

    async def fetch_fees(self, market):
        try:
            response = await self.client.fetch_trading_fee(market)
        except (ccxt.NotSupported, ValueError):
            self.exchange.notify("Error retrieving fee's, using hardcoded...")
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
