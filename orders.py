class OrderBase(object):
    _type = None
    _taker_or_maker = None

    status_none = "NONE"
    status_active = "ACTIVE"
    status_failed = "FAILED"
    status_filled = "FILLED"

    first_price = 0.0
    first_quantity = 0.0

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

        self.actual_price = 0.0
        self.actual_price_with_fee = 0.0
        self.actual_quantity = 0.0

        self.timestamp = None
        self.exchange_order_id = None
        self.status = self.status_none

    def _generate_output(self):
        if self.opportunities:
            return "{}({}, {}, offer={}, best_price={}, best_price_with_fee={}, max_qty={})".format(
                self._type,
                self.exchange_id,
                self.symbol,
                self.best_offer,
                self.best_price,
                self.best_price_with_fee,
                self.best_quantity,
            )
        return "{}({}, {}, first_price={}, first_price_with_fee={}, max_qty={})".format(
            self._type,
            self.exchange_id,
            self.symbol,
            self.first_price,
            self.first_price_with_fee,
            self.first_quantity
        )

    def __repr__(self):
        return self._generate_output()

    def __str__(self):
        return self._generate_output()

    def __lt__(self, other_exchange):
        if self.opportunities and other_exchange.opportunities:
            return self.best_price_with_fee < other_exchange.best_price_with_fee
        return self.first_price_with_fee < other_exchange.first_price_with_fee

    def __le__(self, other_exchange):
        if self.opportunities and other_exchange.opportunities:
            return self.best_price_with_fee <= other_exchange.best_price_with_fee
        return self.first_price_with_fee <= other_exchange.first_price_with_fee

    def __gt__(self, other_exchange):
        if self.opportunities and other_exchange.opportunities:
            return self.best_price_with_fee > other_exchange.best_price_with_fee
        return self.first_price_with_fee > other_exchange.first_price_with_fee

    def __ge__(self, other_exchange):
        if self.opportunities and other_exchange.opportunities:
            return self.best_price_with_fee >= other_exchange.best_price_with_fee
        return self.first_price_with_fee >= other_exchange.first_price_with_fee

    @property
    def first_price_with_fee(self):
        return self._calculate_price_with_fee(self.first_price)

    def _calculate_price_with_fee(self, price):
        return (1.0 + self.exchange_market.trading_fees[self._taker_or_maker]) * price

    def set_opportunity(self, opportunities):
        self.opportunities = sorted(opportunities, key=lambda x: x[-1], reverse=True)
        if opportunities:
            self.best_price = self.opportunities[0][0]
            self.best_price_with_fee = self.opportunities[0][1]
            self.best_quantity = self.opportunities[0][2]
            self.best_offer = self.opportunities[0][3]

    async def sell(self, _id, qty, price):
        return await self._create_order(_id, "sell", qty, price)

    async def buy(self, _id, qty, price):
        return await self._create_order(_id, "buy", qty, price)

    async def _create_order(self, _id, side, qty, price):
        self.status = self.status_active
        async with self.exchange.session_manager:
            success, order_id = await self.exchange.client.create_order(
                _id,
                self.symbol,
                qty,
                price,
                side
            )
            self.exchange_order_id = order_id
            if not success:
                self.status = self.status_failed
            return success

    async def cancel(self):
        async with self.exchange.session_manager:
            return await self.exchange.client.cancel_order(self.exchange_order_id, symbol=self.symbol)

    async def get_status(self):
        async with self.exchange.session_manager:
            result = await self.exchange.client.fetch_order_status(self.exchange_order_id)

            self.actual_price = result["price"]
            self.actual_price_with_fee = result["fee"] / (result["price"] * result["quantity"])
            self.actual_quantity = result["quantity"]
            self.timestamp = result["timestamp"]

            if result["filled"] is True:
                self.status = self.status_filled


class BestOrderBid(OrderBase):
    """
    The bid price is the highest price a potential buyer is willing to pay for a crypto.
    """
    _type = "BID"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, bids):
        super(BestOrderBid, self).__init__(exchange_market, exchange)
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
            bid_price_with_fee = self._calculate_price_with_fee(bid_price)

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


class BestOrderAsk(OrderBase):
    """
    The ask price is the lowest price a would-be seller is willing to accept for a crypto
    """
    _type = "ASK"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, asks):
        super(BestOrderAsk, self).__init__(exchange_market, exchange)
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
            ask_price_with_fee = self._calculate_price_with_fee(ask_price)

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
