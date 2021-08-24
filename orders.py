from abc import ABC

from utils import round_down, rounder


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

        self.fee_overwrite = None
        self.opportunities = {}

        self.price = 0.0
        self.base_qty = 0.0
        self.quote_qty = 0.0
        self.quote_fee = 0.0

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
    def first_base_qty(self):
        return self.order_book[0][1]

    @property
    def first_price_with_fee(self):
        return self._calculate_price_with_fee(self.first_price)

    @property
    def first_quote_qty(self):
        return self._calculate_quote_qty(self.first_base_qty, self.first_price)

    @property
    def first_fee(self):
        return self._calculate_fee(self.first_quote_qty)

    @property
    def first_offer(self):
        return self._calculate_offer(self.first_quote_qty, self.first_fee)

    @staticmethod
    def _calculate_quote_qty(qty, price):
        return qty * price

    def _calculate_fee(self, quote_or_price):
        if self.fee_overwrite is not None:
            fee_factor = self.fee_overwrite
        else:
            fee_factor = self.exchange_market.trading_fees[self._taker_or_maker]

        return quote_or_price * fee_factor

    @staticmethod
    def _calculate_offer(*args):
        raise NotImplementedError()

    @staticmethod
    def _calculate_price_with_fee(*args):
        raise NotImplementedError()

    def _calculate_opportunity(self, opposite_price):
        # Loop all bids in the order book
        cum_base_qty = 0.0
        for row in self.order_book:
            price = row[0]
            base_qty = row[1]

            # Compare the prices from the both exchanges, if this returns True there is no arbitrage
            if self._compare_prices(price, opposite_price):
                break

            cum_base_qty += base_qty
            quote_qty = self._calculate_quote_qty(base_qty, price)
            fee = self._calculate_fee(quote_qty)
            offer = self._calculate_offer(quote_qty, fee)

            self.opportunities[base_qty] = [price, cum_base_qty, offer]

    def _generate_output(self):
        if self.opportunity_found:
            return f"{self._type}({self.exchange_id}, {self.symbol}, best_price={rounder(self.price)}, " \
                   f"base_qty={rounder(self.base_qty)}, quote_qty={rounder(self.quote_qty)}, fee={rounder(self.quote_fee)})"

        return f"{self._type}({self.exchange_id}, {self.symbol}, first_price={rounder(self.first_price)}, " \
               f"base_qty={rounder(self.first_base_qty)}, quote_qty={rounder(self.first_quote_qty)}, " \
               f"fee={rounder(self.first_fee)}))"

    def __repr__(self):
        return self._generate_output()

    def __str__(self):
        return self._generate_output()

    def _get_comparing_offers(self, other_exchange):
        if self.status == self.STATUS_FILLED and other_exchange.status == other_exchange.STATUS_FILLED:
            return self.actual_price_with_fee, other_exchange.actual_price_with_fee
        elif self.opportunity_found and other_exchange.opportunity_found:
            return self.price_with_fee, other_exchange.price_with_fee
        else:
            return self.first_offer, other_exchange.first_offer

    def __lt__(self, other_exchange):
        offer, other_offer = self._get_comparing_offers(other_exchange)
        return offer < other_offer

    def __le__(self, other_exchange):
        offer, other_price = self._get_comparing_offers(other_exchange)
        return offer <= other_offer

    def __gt__(self, other_exchange):
        offer, other_price = self._get_comparing_offers(other_exchange)
        return offer > other_offer

    def __ge__(self, other_exchange):
        offer, other_price = self._get_comparing_offers(other_exchange)
        return offer >= other_offer

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

            self.actual_price = result["price"]
            self.actual_base_qty = result["base_quantity"]

            if result["fee"] is None:
                self.actual_price_with_fee = self._calculate_fee(result["price"])
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

    def _compare_prices(self, *args):
        raise NotImplementedError()


class BestOrderBid(OrderBase, ABC):
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

    def _compare_prices(self, price, price_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return self._calculate_price_with_fee(price) <= price_opposite_exchange

    def calculate_price_with_fee(self, price):
        return price - self._calculate_fee(price)

    @staticmethod
    def _calculate_offer(quote_qty, fee):
        return quote_qty - fee

    def calculate_opportunity(self, *args, **kwargs):
        return self._calculate_opportunity(*args, **kwargs)


class BestOrderAsk(OrderBase, ABC):
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

    def _compare_prices(self, price, price_opposite_exchange):
        # If this is True then there is no arbitrage anymore
        return self._calculate_price_with_fee(price) >= price_opposite_exchange

    def calculate_price_with_fee(self, price):
        return price + self._calculate_fee(price)

    @staticmethod
    def _calculate_offer(quote_qty, fee):
        return quote_qty + fee

    def calculate_opportunity(self, *args, **kwargs):
        self._calculate_opportunity(*args, **kwargs)





