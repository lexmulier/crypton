import json
import pprint
import requests
import time
import logging

from log import Notify

logger = logging.getLogger(__name__)


class BaseAPI:
    def __init__(self, config, exchange=None, *args, **kwargs):
        self.config = config

        if exchange:
            self.exchange = exchange
            self.exchange_id = exchange.exchange_id
            self.notifier = exchange.notifier
        else:
            self.exchange = None
            self.exchange_id = "NO-EXCHANGE-ID"
            self.notifier = Notify(level="info")
            self.notifier.initiate()

        self.debug_mode = logging.root.level == logging.DEBUG

        self.async_session = None
        self.sync_session = requests.Session()

    def debugger(self, **kwargs):
        if self.debug_mode:
            self.notifier.add(
                logger,
                f"############### {self.__class__.__name__}",
                now=True,
                log_level="debug",
            )
            for name, data in kwargs.items():
                self.notifier.add(
                    logger, f"{name.upper()} :", now=True, log_level="debug"
                )
                self.notifier.add(
                    logger, "\n" + pprint.pformat(data), now=True, log_level="debug"
                )
            self.notifier.add(logger, "###############", now=True, log_level="debug")

    async def async_get(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        async with self.async_session.get(url, data=data, headers=headers) as response:
            json_response = await response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    async def async_post(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        headers["Content-Type"] = "application/json"
        async with self.async_session.post(url, data=data, headers=headers) as response:
            json_response = await response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    async def async_delete(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        async with self.async_session.delete(
            url, data=data, headers=headers
        ) as response:
            json_response = await response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    def get(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        with self.sync_session.get(url, data=data, headers=headers) as response:
            json_response = response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    def post(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        headers["Content-Type"] = "application/json"
        with self.sync_session.post(url, data=data, headers=headers) as response:
            json_response = response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    def delete(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        with self.sync_session.delete(url, data=data, headers=headers) as response:
            json_response = response.json()
            self.debugger(url=url, data=data, headers=headers, response=json_response)
            return json_response

    async def fetch_fees(self, *args, **kwargs):
        """
        Args:
            symbol (str): "ETH/BTC"

        Returns:
            dict: {"maker": 0.002, "taker", 0.002}
        """
        raise NotImplementedError("fetch_fees not implemented for this API")

    async def fetch_order_book(self, *args, **kwargs):
        """
        Args:
            symbol (str): "ETH/BTC"
            limit (int): 20, amount of order book lines to return, optional.

        Returns:
            list: Asks [[price, quantity], [price, quantity], ...]
            list: Bids [[price, quantity], [price, quantity], ...]
        """
        raise NotImplementedError("fetch_order_book_async not implemented for this API")

    async def fetch_markets(self, *args, **kwargs):
        """
        Returns:
            dict:
                "symbol": "ETH/BTC"
                "base": "ETH"
                "quote": "BTC"
                "min_base_qty": 100.0
                "min_quote_qty": 0.0001
                "base_precision": 0.001
                "quote_precision": 0.001
                "price_precision": 0.001
        """
        raise NotImplementedError("fetch_markets not implemented for this API")

    async def fetch_balance(self, *args, **kwargs):
        """
        Returns:
            dict: {"ETH": 200.0, "BTC": 2.4, ...}
        """
        raise NotImplementedError("fetch_balance order not implemented for this API")

    async def fetch_order_status(self, *args, **kwargs):
        """
        Args:
            order_id (str): The orderid that was returned from the order, can also be User Order Id

        Returns:
            dict:
                "price": float,
                "base_quantity": float,
                "fee": float (flat, total fee),
                "timestamp": datetime.datetime.now(),
                "filled": bool
        """
        raise NotImplementedError("fetch_order_status not implemented for this API")

    async def fetch_order_history(self, *args, **kwargs):
        """
        Returns:
            response as from the the Exchange API.
        """
        raise NotImplementedError("fetch_order_history not implemented for this API")

    async def create_order(self, *args, **kwargs):
        """
        Args:
            id (str): Custom Order Id
            symbol (str): "ETH/BTC"
            qty (float): 2000.0
            price (float): 0.05
            side (str): "buy" or "sell"

        Returns:
            bool: True if order had a successful response message
            _id: return the (updated) order id coming from the exchange. Needed for order status check.
        """
        raise NotImplementedError("create_order not implemented for this API")

    def cancel_order(self, *args, **kwargs):
        """
        Args:
            order_id (str): Order Id from the exchange (either supplied by us or new by exchange)

        Returns:
            bool: True if the order has return message without error.
        """
        raise NotImplemented("cancel_order is not implemented here")

    @staticmethod
    async def fetch_exchange_specifics():
        return None

    @staticmethod
    def _compact_json_dict(data):
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _nonce():
        return str(int(time.time() * 1000))

    @staticmethod
    def _precision(value):
        if float(value) < 1.0:
            precision = value[::-1].find(".")
        elif float(value) >= 1.0:
            value = str(float(value))
            precision = (value.find(".") * -1) + 1
        else:
            raise ValueError(f"A precision we can't solve! {value}")

        return precision

    @staticmethod
    def _get_params_for_sig(data):
        return "&".join(["{}={}".format(key, data[key]) for key in data])
