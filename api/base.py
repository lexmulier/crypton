import json

import time


class BaseAPI(object):

    def __init__(self, config, exchange=None, *args, **kwargs):
        self.config = config
        self.exchange = exchange
        self.session = None

    def notify(self, *args):
        if self.exchange:
            self.exchange.notify(*args)
        else:
            print(*args)

    async def get(self, url, headers=None):
        headers = headers or {}
        async with self.session.get(url, headers=headers) as response:
            return await response.json()

    async def post(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        headers["Content-Type"] = "application/json"
        async with self.session.post(url, data=data, headers=headers) as response:
            return await response.json()

    async def delete(self, url, data=None, headers=None):
        headers = headers or {}
        data = data or {}
        async with self.session.delete(url, data=data, headers=headers) as response:
            return await response.json()

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
        raise NotImplementedError("fetch_order_book not implemented for this API")

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
        return json.dumps(data, separators=(',', ':'), ensure_ascii=False)

    @staticmethod
    def _nonce():
        return str(int(time.time() * 1000))

    @staticmethod
    def _precision(value):
        if float(value) < 1.0:
            #value = value.rstrip("0")
            precision = value[::-1].find('.')
        elif float(value) >= 1.0:
            value = str(float(value))
            precision = (value.find('.') * -1) + 1
        else:
            raise ValueError("A precision we can't solve! {}".format(value))

        return precision

    @staticmethod
    def _get_params_for_sig(data):
        return '&'.join(["{}={}".format(key, data[key]) for key in data])



