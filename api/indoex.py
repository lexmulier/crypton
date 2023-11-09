from api.base import BaseAPI
from utils import exception_logger


class IndoExAPI(BaseAPI):
    def __init__(self, *args, **kwargs):
        super(IndoExAPI, self).__init__(*args, **kwargs)

    async def get(self, url):
        async with self.async_session.get(url) as response:
            assert response.status == 200
            return await response.json(content_type=None)

    @exception_logger()
    async def fetch_order_book(self, symbol, limit=None):
        url = f"https://api.indoex.io/depth/{symbol.replace('/', '_')}"
        response = await self.async_get(url)
        asks = [[float(x["price"]), float(x["quantity"])] for x in response["asks"]]
        bids = [[float(x["price"]), float(x["quantity"])] for x in response["bids"]]
        return asks, bids

    @exception_logger()
    def fetch_order_book_sync(self, symbol, limit=None):
        url = f"https://api.indoex.io/depth/{symbol.replace('/', '_')}"
        response = self.get(url)
        asks = [[float(x["price"]), float(x["quantity"])] for x in response["asks"]]
        bids = [[float(x["price"]), float(x["quantity"])] for x in response["bids"]]
        return asks, bids

    @exception_logger()
    async def fetch_markets(self):
        url = "https://api.indoex.io/markets/"
        response = await self.async_get(url)
        markets = [
            {
                "symbol": f"{x['base']}/{x['quote']}",
                "base": x["base"],
                "quote": x["quote"],
            }
            for x in response["combinations"]
        ]
        return markets

    @exception_logger()
    async def fetch_balance(self):
        return {}

    @exception_logger()
    async def fetch_fees(self, _):
        self.exchange.log.info("NEEDS IMPROVEMENT")
        return {"maker": 0.1, "taker": 0.2}
