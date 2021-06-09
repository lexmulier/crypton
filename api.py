import hashlib
import hmac
import logging

import time
import base64

import ccxt.async_support as ccxt

# Shut up the stupid closing message from CCXT. I think it's a bug.
logging.getLogger("ccxt").setLevel(logging.CRITICAL)


class APIBase(object):

    def __init__(self, exchange, session, *args, **kwargs):
        self.exchange = exchange
        self.config = exchange.api_config
        self.session = session

    async def request(self, url):
        async with self.session.get(url) as response:
            pass


class KuCoinAPI(APIBase):
    _base_url = "https://api.kucoin.com/api/v1/"

    def __init__(self, exchange, session):
        super(KuCoinAPI, self).__init__(exchange, session)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode('utf-8')
        self._passphrase = self.config["KC-API-PASSPHRASE"].encode('utf-8')
        self._password = self.config["password"]

    @property
    def _encoded_passphrase(self):
        return base64.b64encode(hmac.new(self._secret, self._passphrase, hashlib.sha256).digest())

    def _encoded_signature(self, now, method="GET", location="/api/v1/accounts"):
        return base64.b64encode(
            self._secret,
            str(now) + method + location,
        )

    def _get_headers(self):
        now = str(int(time.time() * 1000))
        return {
            "KC-API-SIGN": self._encoded_signature(now),
            "KC-API-TIMESTAMP": str(now),
            "KC-API-KEY": self._api_key,
            "KC-API-PASSPHRASE": self._encoded_passphrase,
            "KC-API-KEY-VERSION": 2
        }


class CcxtAPI(object):
    def __init__(self, exchange, session):
        self.exchange = exchange
        self.session = session

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

    async def close(self):
        await self.client.close()


def get_client(exchange, session):
    _api_class_mapping = {
        "ascendex": CcxtAPI,
        "binance": CcxtAPI,
        "liquid": CcxtAPI,
        "timex": CcxtAPI,
        "latoken": CcxtAPI,
        "kucoin": CcxtAPI,
        "kraken": CcxtAPI,
        "binance": CcxtAPI
    }

    if exchange.exchange_id not in _api_class_mapping:
        raise ValueError("API wrapper config for {} does not exist".format(exchange.exchange_id))

    wrapper = _api_class_mapping[exchange.exchange_id](exchange, session)
    exchange.notify("Using API {} for {}".format(wrapper.__class__.__name__, exchange.exchange_id))
    return wrapper

