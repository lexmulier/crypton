class TestAPI(object):

    def __init__(
            self,
            side="",
            market=None,
            asks=None,
            bids=None,
            balance=None
    ):
        self.side = side
        self.market = market
        self.asks = asks
        self.bids = bids
        self.balance = balance

    def notify(self, *args):
        print(self.side, *args)

    async def fetch_fees(self, *args, **kwargs):
        return {"maker": 0.002, "taker": 0.002}

    async def fetch_order_book(self, *args, **kwargs):
        return self.asks, self.bids

    async def fetch_markets(self, *args, **kwargs):
        base, quote = self.market.split("/")
        return [{
            "symbol": self.market,
            "base": base,
            "quote": quote,
            "min_base_qty": 0.0,
            "min_quote_qty": 0.0,
            "base_precision": 8,
            "quote_precision": 8,
            "price_precision": 8
        }]

    async def fetch_balance(self, *args, **kwargs):
        return self.balance

    async def fetch_order_status(self, *args, **kwargs):
        """
        Args:
            order_id (str): The orderid that was returned from the order, can also be User Order Id

        Returns:
            dict:
                "price": float,
                "quantity": float,
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
        return
