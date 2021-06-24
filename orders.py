class OrderBase(object):
    _type = None
    _taker_or_maker = None
    _precision = 8

    STATUS_NONE = "NONE"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_FAILED = "FAILED"
    STATUS_FILLED = "FILLED"

    order_book = []

    def __init__(self, exchange_market, exchange):
        self.exchange_market = exchange_market
        self.symbol = exchange_market.symbol
        self.exchange = exchange
        self.exchange_id = exchange.exchange_id

        self.opportunity_found = False

        self.price = 0.0
        self.price_with_fee = 0.0
        self.base_qty = 0.0
        self.quote_qty = 0.0

        self.actual_price = 0.0
        self.actual_price_with_fee = 0.0
        self.actual_base_qty = 0.0
        self.actual_quote_qty = 0.0

        self.timestamp = None
        self.exchange_order_id = None
        self.status = self.STATUS_NONE

    @property
    def first_price(self):
        return self.order_book[0][0]

    @property
    def first_qty(self):
        return self.order_book[0][1]

    @property
    def first_price_with_fee(self):
        return self._calculate_price_with_fee(self.first_price)

    def _generate_output(self):
        if self.opportunity_found:
            return "{}({}, {}, best_price={}, price_with_fee={}, base_qty={}, quote_qty={})".format(
                self._type,
                self.exchange_id,
                self.symbol,
                self.price,
                self.price_with_fee,
                self.base_qty,
                self.quote_qty,
            )
        return "{}({}, {}, first_price={}, first_price_with_fee={}, base_qty={})".format(
            self._type,
            self.exchange_id,
            self.symbol,
            self.first_price,
            self.first_price_with_fee,
            self.first_qty
        )

    def __repr__(self):
        return self._generate_output()

    def __str__(self):
        return self._generate_output()

    def _get_comparing_prices(self, other_exchange):
        if self.status == self.STATUS_FILLED and other_exchange.status == other_exchange.STATUS_FILLED:
            return self.actual_price_with_fee, other_exchange.actual_price_with_fee
        elif self.opportunity_found and other_exchange.opportunity_found:
            return self.price_with_fee, other_exchange.price_with_fee
        else:
            return self.first_price_with_fee, other_exchange.first_price_with_fee

    def __lt__(self, other_exchange):
        price, other_price = self._get_comparing_prices(other_exchange)
        return price < other_price

    def __le__(self, other_exchange):
        price, other_price = self._get_comparing_prices(other_exchange)
        return price <= other_price

    def __gt__(self, other_exchange):
        price, other_price = self._get_comparing_prices(other_exchange)
        return price > other_price

    def __ge__(self, other_exchange):
        price, other_price = self._get_comparing_prices(other_exchange)
        return price >= other_price

    def _calculate_price_with_fee(self, *args):
        raise NotImplementedError()

    async def sell(self, _id, qty, price):
        return await self._create_order(_id, "sell", qty, price)

    async def buy(self, _id, qty, price):
        return await self._create_order(_id, "buy", qty, price)

    async def _create_order(self, _id, side, qty, price):
        self.status = self.STATUS_ACTIVE
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
                self.status = self.STATUS_FAILED
            return success

    async def cancel(self):
        async with self.exchange.session_manager:
            return await self.exchange.client.cancel_order(self.exchange_order_id, symbol=self.symbol)

    async def get_status(self):
        async with self.exchange.session_manager:
            result = await self.exchange.client.fetch_order_status(self.exchange_order_id)

            self.actual_price = result["price"]
            self.actual_price_with_fee = result["fee"] / result["quantity"]
            self.actual_base_qty = result["quantity"]
            self.actual_quote_qty = self.actual_base_qty * self.actual_price_with_fee
            self.timestamp = result["timestamp"]

            if result["filled"] is True:
                self.status = self.STATUS_FILLED

    def _compare_price_opposite_exchange(self, *args):
        raise NotImplementedError()

    def opportunity(self, price_with_fee_opposite_exchange, max_quote_qty=None, max_base_qty=None):
        if max_base_qty is None and max_quote_qty is None:
            raise ValueError("No quantity provided in either base or quote currency")

        self.base_qty = 0.0
        self.quote_qty = 0.0
        # Loop all bids in the response from the exchange
        for row in self.order_book:
            price = row[0]
            base_qty = row[1]

            # Calculate the ask price including the fee
            price_with_fee = self._calculate_price_with_fee(price)

            # Check if the offer price plus fee is better than the highest bid price with fee
            if self._compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
                break

            # Calculate quote currency quantity
            quote_qty = price_with_fee * base_qty

            if max_quote_qty is not None and quote_qty > max_quote_qty:
                # We need to calculate the base quantity based on the quote quantity portion of the trade
                factor = (max_quote_qty / quote_qty)
                base_qty = round(base_qty * factor, self._precision)
                quote_qty = round(quote_qty * factor, self._precision)

            elif max_base_qty is not None and base_qty > max_base_qty:
                # We need to calculate the base quantity based on the quote quantity portion of the trade
                factor = (max_base_qty / base_qty)
                base_qty = base_qty * factor
                quote_qty = quote_qty * factor

            # Set the price to this price
            self.price = price
            self.price_with_fee = price_with_fee
            self.base_qty += base_qty
            self.quote_qty += quote_qty
            self.opportunity_found = True

            # Reduce the balance left by the amount of the current trade
            if max_base_qty is not None:
                max_base_qty -= base_qty
                if max_base_qty <= 0.0:
                    break

            if max_quote_qty is not None:
                max_quote_qty -= quote_qty
                if max_quote_qty <= 0.0:
                    break

        self.price = round(self.price, self._precision)
        self.price_with_fee = round(self.price_with_fee, self._precision)
        self.base_qty = round(self.base_qty, self._precision)
        self.quote_qty = round(self.quote_qty, self._precision)


class BestOrderBid(OrderBase):
    """
    The bid price is the highest price a potential buyer is willing to pay for a crypto.
    """
    _type = "BID"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, bids):
        super(BestOrderBid, self).__init__(exchange_market, exchange)
        self.order_book = self.order_bids(bids)

    @staticmethod
    def order_bids(bids):
        return sorted(bids, key=lambda bid: bid[0], reverse=True)

    def _calculate_price_with_fee(self, price, fee=None):
        fee = fee if fee is not None else self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 - fee) * price, self._precision)

    @staticmethod
    def _compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return price_with_fee <= price_with_fee_opposite_exchange


class BestOrderAsk(OrderBase):
    """
    The ask price is the lowest price a would-be seller is willing to accept for a crypto
    """
    _type = "ASK"
    _taker_or_maker = "taker"

    def __init__(self, exchange_market, exchange, asks):
        super(BestOrderAsk, self).__init__(exchange_market, exchange)
        self.order_book = self.order_asks(asks)

    @staticmethod
    def order_asks(asks):
        return sorted(asks, key=lambda ask: ask[0])

    def _calculate_price_with_fee(self, price, fee=None):
        fee = fee if fee is not None else self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 + fee) * price, self._precision)

    @staticmethod
    def _compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return price_with_fee >= price_with_fee_opposite_exchange
