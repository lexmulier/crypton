class OrderBook(object):
    _type = None
    _taker_or_maker = None
    _default_fee_percentage = 0.005

    first_price = None
    first_quantity = None

    def __init__(self, exchange_market, exchange):
        self.exchange_market = exchange_market
        self.symbol = exchange_market.symbol
        self.exchange = exchange
        self.exchange_id = exchange.exchange_id
        self.opportunities = []
        self.best_price = 0.0
        self.best_price_with_fee = 0.0
        self.best_quantity = 0.0
        self.best_offer = 0.0

    def _generate_output(self):
        return "{}({}, {}, offer={}, price={}, qty={}, first_price={}, first_qty={})".format(
            self._type,
            self.exchange_id,
            self.symbol,
            self.best_offer,
            self.best_price,
            self.best_quantity,
            self.first_price,
            self.first_quantity
        )

    def __repr__(self):
        return self._generate_output()

    def __str__(self):
        return self._generate_output()

    def __lt__(self, other_exchange):
        if self.best_offer and other_exchange.best_offer:
            return self.best_price_with_fee < other_exchange.best_price_with_fee
        return self.price_with_fee < other_exchange.price_with_fee

    def __le__(self, other_exchange):
        if self.best_offer and other_exchange.best_offer:
            return self.best_price_with_fee <= other_exchange.best_price_with_fee
        return self.price_with_fee <= other_exchange.price_with_fee

    def __gt__(self, other_exchange):
        if self.best_offer and other_exchange.best_offer:
            return self.best_price_with_fee > other_exchange.best_price_with_fee
        return self.price_with_fee > other_exchange.price_with_fee

    def __ge__(self, other_exchange):
        if self.best_offer and other_exchange.best_offer:
            return self.best_price_with_fee >= other_exchange.best_price_with_fee
        return self.price_with_fee >= other_exchange.price_with_fee

    @property
    def price_with_fee(self):
        return self._calculate_price_with_fee(self.first_price, self.first_quantity)

    @staticmethod
    # TODO: Check this fee calculation.
    def _find_fee_tier(trading_fees_data, quantity, taker_or_maker='taker'):
        fee_tiers = trading_fees_data['tiers'].get(taker_or_maker)
        if not fee_tiers:
            fee_tiers = trading_fees_data['tiers']['spot'][taker_or_maker]
        # Loop tiers reversed to simplify the check
        for tier in fee_tiers[::-1]:
            if quantity >= tier[0]:
                return tier[1]
        # Return first tier if nothing matched
        return fee_tiers[0][1]

    def _calculate_price_with_fee(self, price, quantity):
        trading_fees_data = self.exchange_market.trading_fees
        if trading_fees_data.get('tierBased', False) is True and trading_fees_data.get('tiers'):
            trading_fee = self._find_fee_tier(trading_fees_data, quantity, taker_or_maker=self._taker_or_maker)
        else:
            trading_fee = trading_fees_data[self._taker_or_maker]

        if trading_fees_data.get('percentage', True) is True:
            trading_fee = trading_fee if trading_fee is not None else self._default_fee_percentage
            return price * (1.0 + trading_fee)
        else:
            return price + trading_fee

    def set_opportunity(self, opportunities):
        self.opportunities = sorted(opportunities, key=lambda x: x[-1], reverse=True)
        if opportunities:
            self.best_price = self.opportunities[0][0]
            self.best_price_with_fee = self.opportunities[0][1]
            self.best_quantity = self.opportunities[0][2]
            self.best_offer = self.opportunities[0][3]


class BestOrderBookBid(OrderBook):
    """
    The bid price is the highest price a potential buyer is willing to pay for a crypto.
    """
    _type = "BID"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, bids):
        super(BestOrderBookBid, self).__init__(exchange_market, exchange)
        self.bids = self.order_bids(bids)

    @staticmethod
    def order_bids(bids):
        return sorted(bids, key=lambda bid: bid[0], reverse=True)

    @property
    def first_price(self):
        return self.bids[0][0]

    @property
    def first_quantity(self):
        return self.bids[0][1]

    def opportunity(self, lowest_ask_price_with_fee, balance_qty, min_qty):
        opportunities = []
        # Loop all bids in the response from the exchange
        for bid_row in self.bids:
            bid_price = bid_row[0]
            bid_qty = bid_row[1]

            # Maximum quantity is either set by the quantity of the offer, or what we have in our balance
            max_possible_qty = min(bid_qty, balance_qty)

            # If the maximum possible quantity is lower than what we allow, continue
            if min_qty > max_possible_qty:
                continue

            # Calculate the bid price including the fee
            bid_price_with_fee = self._calculate_price_with_fee(bid_price, max_possible_qty)

            # Check if the offer price plus fee is better than the highest asking price with fee
            if bid_price_with_fee > lowest_ask_price_with_fee:

                # Calculate the opportunity for this particular offer
                opportunities.append([
                    bid_price,
                    bid_price_with_fee,
                    max_possible_qty,
                    bid_price_with_fee * max_possible_qty
                ])

        self.set_opportunity(opportunities)


class BestOrderBookAsk(OrderBook):
    """
    The ask price is the lowest price a would-be seller is willing to accept for a crypto
    """
    _type = "ASK"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, asks):
        super(BestOrderBookAsk, self).__init__(exchange_market, exchange)
        self.asks = self.order_asks(asks)

    @staticmethod
    def order_asks(asks):
        return sorted(asks, key=lambda ask: ask[0])

    @property
    def first_price(self):
        return self.asks[0][0]

    @property
    def first_quantity(self):
        return self.asks[0][1]

    def opportunity(self, highest_bid_price_with_fee, balance_qty, min_qty):
        opportunities = []
        # Loop all bids in the response from the exchange
        for ask_row in self.asks:
            ask_price = ask_row[0]
            ask_qty = ask_row[1]

            # Maximum quantity is either set by the quantity of the offer, or what we have in our balance
            max_possible_qty = min(ask_qty, balance_qty)

            # If the maximum possible quantity is lower than what we allow, continue
            if min_qty > max_possible_qty:
                continue

            # Calculate the ask price including the fee
            ask_price_with_fee = self._calculate_price_with_fee(ask_price, ask_qty)

            # Check if the offer price plus fee is better than the highest bid price with fee
            if ask_price_with_fee < highest_bid_price_with_fee:

                # Calculate the opportunity for this particular offer
                opportunities.append([
                    ask_price,
                    ask_price_with_fee,
                    max_possible_qty,
                    ask_price_with_fee * max_possible_qty
                ])

        self.set_opportunity(opportunities)
