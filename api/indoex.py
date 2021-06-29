from api.base import BaseAPI


class IndoExAPI(BaseAPI):
    def __init__(self, *args, **kwargs):
        super(IndoExAPI, self).__init__(*args, **kwargs)

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

    async def fetch_balance(self):
        return {}

    async def fetch_fees(self, _):
        self.exchange.log.info("NEEDS IMPROVEMENT")
        return {"maker": 0.1, "taker": 0.2}