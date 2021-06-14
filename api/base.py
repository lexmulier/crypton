import time


class APIBase(object):

    def __init__(self, exchange, *args, **kwargs):
        self.exchange = exchange
        self.config = exchange.api_config
        self.config = exchange.api_config
        self.session = None

    async def get(self, url, headers=None):
        headers = headers or {}
        async with self.session.get(url, headers=headers) as response:
            return await response.json()

    async def post(self, url, data, headers=None):
        headers = headers or {}
        headers["Content-Type"] = "application/json"
        async with self.session.post(url, data=data, headers=headers) as response:
            return await response.json()

    async def fetch_balance(self):
        self.exchange.notify("Using not implemented fetch_balance")
        return {}

    async def fetch_fees(self, _):
        self.exchange.notify("Using not implemented fetch_fees")
        return {"maker": 0.2, "taker": 0.2}

    @staticmethod
    async def fetch_exchange_specifics():
        return None

    @staticmethod
    def _nonce():
        return str(int(time.time() * 1000))
