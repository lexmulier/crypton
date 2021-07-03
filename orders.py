class OrderBase(object):
    _type = None
    _taker_or_maker = None

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
        self.fee_overwrite = None

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
            return f"{self._type}({self.exchange_id}, {self.symbol}, " \
                   f"best_price={self.price:.10f}, price_with_fee={self.price_with_fee:.10f}, " \
                   f"base_qty={self.base_qty:.10f}, quote_qty={self.quote_qty:.10f})"

        return f"{self._type}({self.exchange_id}, {self.symbol}, " \
               f"first_price={self.first_price:.10f}, first_price_with_fee={self.first_price_with_fee:.10f}, " \
               f"base_qty={self.first_qty:.10f})"

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
            result = await self.exchange.client.fetch_order_status(self.exchange_order_id, symbol=self.symbol)

            if not result or "price" not in result:
                return

            self.actual_price = round(
                result["price"], self.exchange_market.price_precision
            )
            self.actual_base_qty = round(
                result["base_quantity"], self.exchange_market.base_precision
            )

            if result["fee"] is None:
                self.actual_price_with_fee = self._calculate_price_with_fee(result["price"])
            else:
                self.actual_price_with_fee = round(
                    result["price"] + (result["fee"] / result["base_quantity"]),
                    self.exchange_market.price_precision
                )
            self.actual_quote_qty = round(
                self.actual_base_qty * self.actual_price_with_fee, self.exchange_market.quote_precision
            )
            self.timestamp = result["timestamp"]

            if result["filled"] is True:
                self.status = self.STATUS_FILLED

    def _compare_price_opposite_exchange(self, *args):
        raise NotImplementedError()

    def _opportunity(self, price_with_fee_opposite_exchange, max_quote_qty=None, max_base_qty=None):
        self.base_qty = 0.0
        self.quote_qty = 0.0

        # Loop all bids in the order book
        for row in self.order_book:
            price = row[0]
            base_qty = row[1]

            # Calculate the ask price including the fee
            price_with_fee = self._calculate_price_with_fee(price)

            # Compare the prices from the both exchanges, if this returns True there is no arbitrage
            if self._compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
                break

            # Calculate quote currency quantity
            quote_qty = price_with_fee * base_qty

            if max_quote_qty is not None and quote_qty > max_quote_qty:
                # We need to calculate the base quantity based on the quote quantity portion of the trade
                factor = (max_quote_qty / quote_qty)
                base_qty = base_qty * factor
                quote_qty = quote_qty * factor

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

        # Round all numbers
        self.price = round(self.price, self.exchange_market.price_precision)
        self.price_with_fee = round(self.price_with_fee, self.exchange_market.price_precision)


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

    def _calculate_price_with_fee(self, price):
        if self.fee_overwrite is not None:
            fee = self.fee_overwrite
        else:
            fee = self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 - fee) * price, self.exchange_market.price_precision)

    @staticmethod
    def _compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return price_with_fee <= price_with_fee_opposite_exchange

    def opportunity(self, *args, **kwargs):
        self._opportunity(*args, **kwargs)


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

    def _calculate_price_with_fee(self, price):
        if self.fee_overwrite is not None:
            fee = self.fee_overwrite
        else:
            fee = self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 + fee) * price, self.exchange_market.price_precision)

    @staticmethod
    def _compare_price_opposite_exchange(price_with_fee, price_with_fee_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return price_with_fee >= price_with_fee_opposite_exchange

    def opportunity(self, *args, **kwargs):
        self._opportunity(*args, **kwargs)

        # Some exchanges don't want to get an order with a quote qty that is calculated using
        # order_book layers. It needs available on balance the highest price * base qty
        if not self.exchange.layered_quote_qty_calc:
            self.quote_qty = round(self.price_with_fee * self.base_qty, self.exchange_market.quote_precision)


