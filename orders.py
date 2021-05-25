class OrderBook(object):
    price = None
    quantity = None

    def __init__(self, exchange_market, exchange):
        self.exchange_market = exchange_market
        self.symbol = exchange_market.symbol
        self.exchange = exchange
        self.exchange_id = exchange.exchange_id

    def _generate_output(self):
        return "{}(exchange={}, symbol={}, price={}, quantity={})".format(
            self.__class__.__name__,
            self.exchange_id,
            self.symbol,
            self.price,
            self.quantity
        )

    def __repr__(self):
        return self._generate_output()

    def __str__(self):
        return self._generate_output()

    def __lt__(self, other_exchange):
        return self.price_with_fee < other_exchange.price_with_fee

    def __le__(self, other_exchange):
        return self.price_with_fee <= other_exchange.price_with_fee

    def __gt__(self, other_exchange):
        return self.price_with_fee > other_exchange.price_with_fee

    def __ge__(self, other_exchange):
        return self.price_with_fee >= other_exchange.price_with_fee

    @property
    def price_with_fee(self):
        return self._calculate_price_with_fee(self.price, self.quantity)

    @staticmethod
    def _find_fee_tier(trading_fees_data, quantity, taker_or_maker='taker'):
        fee_tiers = trading_fees_data['tiers'][taker_or_maker]
        # Loop tiers reversed to simplify the check
        for tier in fee_tiers[::-1]:
            if quantity >= tier[0]:
                return tier[1]
        # Return first tier if nothing matched
        return fee_tiers[0][1]

    def _calculate_price_with_fee(self, price, quantity, taker_or_maker='taker'):
        trading_fees_data = self.exchange_market.trading_fees
        if trading_fees_data.get('tierBased', False) is True:
            trading_fee = self._find_fee_tier(trading_fees_data, quantity, taker_or_maker=taker_or_maker)
        else:
            trading_fee = trading_fees_data[taker_or_maker]

        if trading_fees_data.get('percentage', True) is True:
            return price * (1.0 + trading_fee)
        else:
            return price + trading_fee


class BestOrderBookBid(OrderBook):
    """
    The bid price is the highest price a potential buyer is willing to pay for a crypto.
    """

    def __init__(self, exchange_market, exchange, bids):
        super(BestOrderBookBid, self).__init__(exchange_market, exchange)
        self.bids = self.order_bids(bids)
        # TODO: Add option to include all Bids where there is arbitrage, not just the best one.
        # It might mean that there is more profit in amount because the order is larger.

    @staticmethod
    def order_bids(bids):
        return sorted(bids, key=lambda bid: bid[0], reverse=True)

    @property
    def price(self):
        return self.bids[0][0]

    @property
    def quantity(self):
        return self.bids[0][1]

    def opportunity(self, lowest_ask_price_with_fee):
        for bid, quantity in self.bids:
            bid_with_fee =
            if bid > lowest_ask_price_with_fee:



        valid_bids = [bid for bid in self.bids if bid[0] > lowest_ask_price]



class BestOrderBookAsk(OrderBook):
    """
    The ask price is the lowest price a would-be seller is willing to accept for a crypto
    """

    def __init__(self, exchange_market, exchange, asks):
        super(BestOrderBookAsk, self).__init__(exchange_market, exchange)
        self.asks = self.order_asks(asks)
        # TODO: Add option to include all Asks where there is arbitrage, not just the best one.
        # It might mean that there is more profit in amount because the order is larger.

    @staticmethod
    def order_asks(asks):
        return sorted(asks, key=lambda ask: ask[0])

    @property
    def price(self):
        return self.asks[0][0]

    @property
    def quantity(self):
        return self.asks[0][1]
