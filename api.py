import asyncio
import aiohttp

import ccxt



class WrapperBase(object):

    def __init__(self, *args, **kwargs):
        pass


class CcxtAPI(WrapperBase):

    def __init__(self, exchange, *args, **kwargs):
        super(CcxtAPI, self).__init__(*args, **kwargs)
        self.exchange = exchange

    @property
    def client(self):
        exchange_class = getattr(ccxt, self.exchange.exchange_id)
        return exchange_class(self.exchange.api_config)

    def fetch_fees(self, symbol):
        try:
            response = self.client.fetch_trading_fee(symbol)
        except (ccxt.NotSupported, ValueError):
            self.exchange.notify("Error retrieving fee's, using hardcoded...")
            response = self.client.fees.get('trading', {})

        if 'maker' not in response or 'taker' not in response:
            raise ValueError("API is different than expected: no maker or taker fees")

        return response['maker'], response['taker']

    def fetch_markets(self):
        return self.client.fetch_markets()

    def fetch_balance(self):
        response = self.client.fetch_balance()
        balance_data = response.get("info")

        balance = dict()
        if isinstance(balance_data, list):
            pass

        elif isinstance(balance_data, dict):
            balance = {row["asset"]: float(row["free"]) for row in balance_data.get("balances", {})}

        return balance



def get_client(exchange):
    _api_class_mapping = {
        #"binance": BinanceAPI,
        "binance": CcxtAPI,
    }

    if exchange.exchange_id not in _api_class_mapping:
        raise ValueError("API wrapper config for {} does not exist".format(exchange.exchange_id))

    wrapper = _api_class_mapping[exchange.exchange_id](exchange)
    return wrapper


"""
from exchanges import *
from api import *
from config import *

exchange = Exchange("binance", BINANCE_CONFIG, verbose=True)
client = get_client(exchange)

"""
