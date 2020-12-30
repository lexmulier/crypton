class OrderBook(object):
    def __init__(self, exchange, market_symbol, asks, bids):
        self.exchange = exchange
        self.market_symbol = market_symbol
        self.asks = asks
        self.bids = bids

        self.order_asks_and_bids()

    def order_asks_and_bids(self):
        # TODO: Check if necessary, ordering takes time
        self.asks = sorted(self.asks, key=lambda ask: ask[0])
        self.bids = sorted(self.bids, key=lambda bid: bid[0], reverse=True)

    @property
    def ask_price(self):
        return self.asks[0][0]

    @property
    def ask_qty(self):
        return self.asks[0][1]

    @property
    def ask_id(self):
        if len(self.asks[0]) == 3:
            return self.asks[0][2]
        return None

    @property
    def bid_price(self):
        return self.bids[0][0]

    @property
    def bid_qty(self):
        return self.bids[0][1]

    @property
    def bid_id(self):
        if len(self.bids[0]) == 3:
            return self.bids[0][2]
        return None

    def __lt__(self, other_exchange):
        return self.ask_price < other_exchange.ask_price

    def __le__(self, other_exchange):
        return self.ask_price <= other_exchange.ask_price

    def __eq__(self, other_exchange):
        return self.ask_price == other_exchange.ask_price and self.bid_price == other_exchange.bid_price

    def __ne__(self, other_exchange):
        return self.ask_price != other_exchange.ask_price and self.bid_price != other_exchange.bid_price

    def __gt__(self, other_exchange):
        return self.bid_price > other_exchange.bid_price

    def __ge__(self, other_exchange):
        return self.bid_price >= other_exchange.bid_price

    def __str__(self):
        return str({
            'exchange_id': self.exchange.exchange_id,
            'market_symbol': self.market_symbol,
            'ask_price': self.ask_price,
            'ask_qty': self.ask_qty,
            'ask_id': self.ask_id,
            'bid_price': self.bid_price,
            'bid_qty': self.bid_qty,
            'bid_id': self.bid_id,
        })