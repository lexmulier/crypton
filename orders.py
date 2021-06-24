class OrderBase(object):
    _type = None
    _taker_or_maker = None
    _precision = 8

    STATUS_NONE = "NONE"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_FAILED = "FAILED"
    STATUS_FILLED = "FILLED"

    first_price = 0.0
    first_quantity = 0.0

    def __init__(self, exchange_market, exchange):
        self.exchange_market = exchange_market
        self.symbol = exchange_market.symbol
        self.exchange = exchange
        self.exchange_id = exchange.exchange_id

        self.opportunity_found = False

        self.best_price = 0.0
        self.best_price_with_fee = 0.0
        self.best_base_qty = 0.0
        self.best_quote_qty = 0.0

        self.actual_price = 0.0
        self.actual_price_with_fee = 0.0
        self.actual_quantity = 0.0

        self.timestamp = None
        self.exchange_order_id = None
        self.status = self.STATUS_NONE

    def _generate_output(self):
        if self.opportunity_found:
            return "{}({}, {}, offer={}, best_price={}, best_price_with_fee={}, max_qty={})".format(
                self._type,
                self.exchange_id,
                self.symbol,
                self.best_quote_qty,
                self.best_price,
                self.best_price_with_fee,
                self.best_base_qty,
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

    def _get_comparing_prices(self, other_exchange):
        if self.status == self.STATUS_FILLED and other_exchange.status == other_exchange.STATUS_FILLED:
            return self.actual_price_with_fee, other_exchange.actual_price_with_fee
        elif self.opportunity_found and other_exchange.opportunity_found:
            return self.best_price_with_fee, other_exchange.best_price_with_fee
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

    @property
    def first_price_with_fee(self):
        return self._calculate_price_with_fee(self.first_price)

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
            self.actual_quantity = result["quantity"]
            self.timestamp = result["timestamp"]

            if result["filled"] is True:
                self.status = self.STATUS_FILLED


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

    def _calculate_price_with_fee(self, price, fee=None):
        fee = fee if fee is not None else self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 - fee) * price, self._precision)

    def opportunity(self, lowest_ask_price_with_fee, base_balance_qty_left):
        self.best_base_qty = 0.0
        self.best_quote_qty = 0.0
        # Loop all bids in the response from the exchange
        for bid_row in self.bids:
            bid_price = bid_row[0]
            bid_base_qty = bid_row[1]

            # Calculate the bid price including the fee
            bid_price_with_fee = self._calculate_price_with_fee(bid_price)

            # Check if the offer price plus fee is better than the highest asking price with fee
            if bid_price_with_fee <= lowest_ask_price_with_fee:
                break

            # Calculate quote currency quantity
            trade_quote_qty = bid_price_with_fee * bid_base_qty

            if bid_base_qty > base_balance_qty_left:
                trade_quote_qty = trade_quote_qty * (base_balance_qty_left / bid_base_qty)
                trade_base_qty = base_balance_qty_left
            else:
                trade_base_qty = bid_base_qty

            # Set the price to this price
            self.best_price = bid_price
            self.best_price_with_fee = bid_price_with_fee
            self.best_base_qty += trade_base_qty
            self.best_quote_qty += trade_quote_qty
            self.opportunity_found = True

            # Reduce the balance left by the amount of the current trade
            base_balance_qty_left -= bid_base_qty

            # If we used all the balance we have we stop the search
            if base_balance_qty_left <= 0.0:
                break


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

    def _calculate_price_with_fee(self, price, fee=None):
        fee = fee if fee is not None else self.exchange_market.trading_fees[self._taker_or_maker]
        return round((1.0 + fee) * price, self._precision)

    def opportunity(self, highest_bid_price_with_fee, quote_balance_qty_left):
        self.best_base_qty = 0.0
        self.best_quote_qty = 0.0
        # Loop all bids in the response from the exchange
        for ask_row in self.asks:
            ask_price = ask_row[0]
            ask_base_qty = ask_row[1]

            # Calculate the ask price including the fee
            ask_price_with_fee = self._calculate_price_with_fee(ask_price)

            # Check if the offer price plus fee is better than the highest bid price with fee
            if ask_price_with_fee >= highest_bid_price_with_fee:
                break

            # Calculate quote currency quantity
            trade_quote_qty = round(ask_price_with_fee * ask_base_qty, self._precision)

            if trade_quote_qty > quote_balance_qty_left:
                # We need to calculate the base quantity based on the quote quantity portion of the trade
                ask_base_qty = ask_base_qty * (quote_balance_qty_left / trade_quote_qty)
                # Set the trade quote quantity to whatever is left
                trade_quote_qty = quote_balance_qty_left

            # Set the price to this price
            self.best_price = ask_price
            self.best_price_with_fee = ask_price_with_fee
            self.best_base_qty += ask_base_qty
            self.best_quote_qty += trade_quote_qty
            self.opportunity_found = True

            # Reduce the balance left by the amount of the current trade
            quote_balance_qty_left -= trade_quote_qty

            # If we used all the balance we have we stop the search
            if quote_balance_qty_left <= 0.0:
                break