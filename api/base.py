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

    async def fetch_fees(self, _):
        self.notify("Using not implemented fetch_fees")
        return {"maker": 0.2, "taker": 0.2}

    async def fetch_balance(self, *args, **kwargs):
        raise NotImplementedError("Create order not implemented for this API")

    async def fetch_order_status(self, _):
        raise NotImplementedError("Fetch order status not implemented for this API")

    async def create_order(self, *args, **kwargs):
        raise NotImplementedError("Create order not implemented for this API")

    @staticmethod
    async def fetch_exchange_specifics():
        return None

    @staticmethod
    def _compact_json_dict(data):
        return json.dumps(data, separators=(',', ':'), ensure_ascii=False)

    @staticmethod
    def _nonce():
        return str(int(time.time() * 1000))

    def cancel_order(self, order_id, *args, **kwargs):
        raise NotImplemented("cancel_order is not implemented here")
