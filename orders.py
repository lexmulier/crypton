class OrderBook(object):
    def __init__(self, exchange_market, exchange):
        self.exchange_market = exchange_market
        self.symbol = exchange_market.symbol
        self.exchange = exchange
        self.exchange_id = exchange.exchange_id

    @staticmethod
    def find_fee_tier(trading_fees_data, quantity, taker_or_maker='taker'):
        fee_tiers = trading_fees_data['tiers'][taker_or_maker]
        # Loop tiers reversed to simplify the check
        for tier in fee_tiers[::-1]:
            if quantity >= tier[0]:
                return tier[1]
        # Return first tier if nothing matched
        return fee_tiers[0][1]

    def calculate_price_with_fee(self, price, quantity, taker_or_maker='taker'):
        trading_fees_data = self.exchange_market.trading_fees
        if trading_fees_data.get('tierBased', False) is True:
            trading_fee = self.find_fee_tier(trading_fees_data, quantity, taker_or_maker=taker_or_maker)
        else:
            trading_fee = trading_fees_data[taker_or_maker]

        if trading_fees_data.get('percentage', True) is True:
            return price * (1.0 + trading_fee)
        else:
            return price + trading_fee


class BestOrderBookBid(OrderBook):

    def __init__(self, exchange_market, exchange, bids):
        OrderBook.__init__(self, exchange_market, exchange)
        self.bids = self.order_bids(bids)

    @staticmethod
    def order_bids(bids):
        return sorted(bids, key=lambda bid: bid[0], reverse=True)

    @property
    def price(self):
        return self.bids[0][0]

    @property
    def quantity(self):
        return self.bids[0][1]

    @property
    def price_with_fee(self):
        return self.calculate_price_with_fee(self.price, self.quantity)

    @property
    def cost_with_fee(self):
        return self.quantity * self.price_with_fee

    def __lt__(self, other_exchange):
        return self.price_with_fee < other_exchange.price_with_fee

    def __le__(self, other_exchange):
        return self.price_with_fee <= other_exchange.price_with_fee

    def __gt__(self, other_exchange):
        return self.price_with_fee > other_exchange.price_with_fee

    def __ge__(self, other_exchange):
        return self.price_with_fee >= other_exchange.price_with_fee


class BestOrderBookAsk(OrderBook):

    def __init__(self, exchange_market, exchange, asks):
        OrderBook.__init__(self, exchange_market, exchange)
        self.asks = self.order_asks(asks)

    @staticmethod
    def order_asks(asks):
        return sorted(asks, key=lambda ask: ask[0])

    @property
    def price(self):
        return self.asks[0][0]

    @property
    def quantity(self):
        return self.asks[0][1]

    @property
    def price_with_fee(self):
        return self.calculate_price_with_fee(self.price, self.quantity)

    @property
    def cost_with_fee(self):
        return self.quantity * self.price_with_fee

    def __lt__(self, other_exchange):
        return self.price_with_fee < other_exchange.price_with_fee

    def __le__(self, other_exchange):
        return self.price_with_fee <= other_exchange.price_with_fee

    def __gt__(self, other_exchange):
        return self.price_with_fee > other_exchange.price_with_fee

    def __ge__(self, other_exchange):
        return self.price_with_fee >= other_exchange.price_with_fee