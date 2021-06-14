from api.base import APIBase


class IndoExAPI(APIBase):
    def __init__(self, exchange, session):
        super(IndoExAPI, self).__init__(exchange, session)

    async def get(self, url):
        async with self.session.get(url) as response:
            assert response.status == 200
            return await response.json(content_type=None)

    async def fetch_order_book(self, symbol, limit=None):
        url = "https://api.indoex.io/depth/{}".format(symbol.replace("/", "_"))
        response = await self.get(url)
        asks = [[float(x["price"]), float(x["quantity"])] for x in response["asks"]]
        bids = [[float(x["price"]), float(x["quantity"])] for x in response["bids"]]
        return asks, bids

    async def fetch_markets(self):
        url = "https://api.indoex.io/markets/"
        response = await self.get(url)
        markets = [
            {"symbol": "{}/{}".format(x["base"], x["quote"]), "base": x["base"], "quote": x["quote"]}
            for x in response["combinations"]
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