class OrderBook(object):
    def __init__(self, exchange_market, exchange, asks, bids):
        self.exchange_market = exchange_market
        self.exchange = exchange
        self.asks = asks
        self.bids = bids

        self.order_asks_and_bids()

    def order_asks_and_bids(self):
        self.asks = sorted(self.asks, key=lambda ask: ask[0])
        self.bids = sorted(self.bids, key=lambda bid: bid[0], reverse=True)

    @property
    def ask_price(self):
        return self.asks[0][0]

    @property
    def bid_price(self):
        return self.bids[0][0]

    @property
    def ask_quantity(self):
        return self.asks[0][1]

    @property
    def bid_quantity(self):
        return self.bids[0][1]

    @property
    def ask_id(self):
        if len(self.asks[0]) == 3:
            return self.asks[0][2]
        return None

    @property
    def bid_id(self):
        if len(self.bids[0]) == 3:
            return self.bids[0][2]
        return None

    @property
    def ask_price_with_fee(self):
        return self.calculate_price_with_fee(self.ask_price, self.ask_quantity)

    @property
    def bid_price_with_fee(self):
        return self.calculate_price_with_fee(self.bid_price, self.bid_quantity)

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

    def __lt__(self, other_exchange):
        return self.ask_price_with_fee < other_exchange.ask_price_with_fee

    def __le__(self, other_exchange):
        return self.ask_price_with_fee <= other_exchange.ask_price_with_fee

    def __eq__(self, other_exchange):
        return self.exchange.exchange_id == other_exchange.exchange.exchange_id

    def __ne__(self, other_exchange):
        return self.exchange.exchange_id != other_exchange.exchange.exchange_id

    def __gt__(self, other_exchange):
        return self.bid_price_with_fee > other_exchange.bid_price_with_fee

    def __ge__(self, other_exchange):
        return self.bid_price_with_fee >= other_exchange.bid_price_with_fee

    def __str__(self):
        return str({
            'exchange_id': self.exchange.exchange_id,
            'market_symbol': self.exchange_market.symbol,
            'ask_price': self.ask_price,
            'ask_qty': self.ask_quantity,
            'ask_id': self.ask_id,
            'bid_price': self.bid_price,
            'bid_qty': self.bid_quantity,
            'bid_id': self.bid_id,
        })