import requests

from api.base import APIBase


class DexTradeAPI(APIBase):
    def __init__(self, exchange, session):
        super(DexTradeAPI, self).__init__(exchange, session)
        self.token, self.secret = self._login()

    def _login(self):
        url = "https://api.dex-trade.com/v1/login"
        response = requests.post(url, json=self.config).json()
        return response["token"], response["data"]["secret"]

    async def fetch_order_book(self, symbol, limit=None):
        url = "https://api.dex-trade.com/v1/public/book?pair={}".format(symbol.replace("/", ""))
        response = await self.get(url)
        asks = [[x["rate"], x["volume"]] for x in response["data"]["sell"]]
        bids = [[x["rate"], x["volume"]] for x in response["data"]["buy"]]
        return asks, bids

    async def fetch_markets(self):
        url = "https://api.dex-trade.com/v1/public/symbols"
        response = await self.get(url)
        markets = [
            {"symbol": "{}/{}".format(x["base"], x["quote"]), "base": x["base"], "quote": x["quote"]}
            for x in response["data"]
        ]
        return markets

    # TODO: WIP
    async def fetch_balance(self):
        self.exchange.notify("NEEDS IMPROVEMENT")
        # url = "https://api.dex-trade.com/v1/private/balances"
        # response = await self.get(url)
        # balance = {row["asset"]: float(row["free"]) for row in response.get("balances", {})}
        return {}

    async def fetch_fees(self, _):
        self.exchange.notify("NEEDS IMPROVEMENT")
        return {"maker": 0.1, "taker": 0.2}