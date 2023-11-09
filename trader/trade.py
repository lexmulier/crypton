import asyncio
import datetime
import logging

from bson import ObjectId

from log import Notify, output_logs
from models import db
from trader.messages import (
    ExchangeBalance,
    NotEnoughBalance,
    TakingQuantityFrom,
    ArbitrageSameExchange,
    NoArbitrage,
    BelowMinimalQty,
    BelowMinProfitPerc,
    BelowMinProfitAmount,
    OrderProfit,
    OrderInfo,
    OrderSuccessful,
    OrderFailed,
    StartProcess,
)
from utils import sleep_now, rounder, round_down

logger = logging.getLogger(__name__)


class CryptonTrade:
    MIN_PROFIT_PERC = 0.01
    MIN_PROFIT_AMOUNT = 0.0

    def __init__(
        self,
        market,
        exchanges,
        market_pair_id=None,
        performance_mode=False,
        simulate=False,
        notifier=None,
    ):
        self.market = market
        self.base_coin, self.quote_coin = market.split("/")
        self.exchanges = exchanges

        self.market_pair_id = (
            market_pair_id or "_".join([*sorted(exchanges), market]).upper()
        )
        self.performance_mode = performance_mode
        self.simulate = simulate

        if notifier is None:
            self.notifier = Notify(level="info")
            self.notifier.initiate()
        else:
            self.notifier = notifier

        self.trade_id = ObjectId()
        self.timestamp = datetime.datetime.now()

        self.successful = None
        self.ask = None
        self.bid = None
        self.min_base_qty = None
        self.min_quote_qty = None
        self.base_precision = None
        self.quote_precision = None

        self.bid_base_exchange_qty = 0.0
        self.ask_quote_exchange_qty = 0.0
        self.bid_base_order_qty = 0.0
        self.ask_quote_order_qty = 0.0

        self.expected_profit_perc = None
        self.expected_profit_amount = None
        self.actual_profit_perc = None
        self.actual_profit_amount = None

        self.ordering = False

    @output_logs()
    def start(self, best_asks=None, best_bids=None, simulate=False):
        self.notifier.add(logger, StartProcess(self.trade_id))
        self.set_order_books(best_asks, best_bids)

        # Find the best ask price and bid price on the two exchanges
        self.determine_min_qty_and_precision()

        # Get the balance on the exchanges
        if not self.get_exchange_balances():
            self.save_to_database()
            return

        # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
        self.get_best_opportunity()

        # Check if there is arbitrage and adequate profit
        if not self.verify_arbitrage_and_profit():
            self.save_to_database()
            return

        if simulate:
            return

        # Place the orders
        self.initiate_orders()

        # Check if orders have been filled successfully
        self.verify_orders()

        # Save full order information to the MongoDB database
        self.save_to_database(force=True)

        # Update balance quickly with best guess
        self.update_balance_after_trade()

    def update_balance_after_trade(self):
        self.ask.exchange.balance[self.quote_coin] -= self.ask_quote_order_qty
        self.bid.exchange.balance[self.base_coin] -= self.bid_base_order_qty

    def set_order_books(self, best_asks=None, best_bids=None):
        # Pick the ask and bid exchange based on arbitrage.
        if best_asks and best_bids:
            self.ask = min(best_asks)
            self.bid = max(best_bids)
        else:
            self.fetch_orders()

        self.notifier.add(logger, self.ask)
        self.notifier.add(logger, self.bid)

    def fetch_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [
            exchange.markets[self.market].get_orders_async()
            for exchange in self.exchanges.values()
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        success_exchange1, best_ask_exchange1, best_bid_exchange1 = response[0]
        success_exchange2, best_ask_exchange2, best_bid_exchange2 = response[1]

        if not success_exchange1 and not success_exchange2:
            return False

        # Pick the ask and bid exchange based on arbitrage.
        self.ask = min([best_ask_exchange1, best_ask_exchange2])
        self.bid = max([best_bid_exchange1, best_bid_exchange2])

        self.notifier.add(logger, self.ask)
        self.notifier.add(logger, self.bid)

        return True

    def determine_min_qty_and_precision(self):
        # Now ask and bid are known, set the minimal quantity and precision from the exchange if not forced by user
        ask_exchange_market = self.ask.exchange.markets[self.market]
        bid_exchange_market = self.bid.exchange.markets[self.market]

        self.min_base_qty = max(
            ask_exchange_market.min_base_qty, bid_exchange_market.min_base_qty
        )
        self.min_quote_qty = max(
            ask_exchange_market.min_quote_qty, bid_exchange_market.min_quote_qty
        )
        self.base_precision = min(
            ask_exchange_market.base_precision, bid_exchange_market.base_precision
        )
        self.quote_precision = min(
            ask_exchange_market.quote_precision, bid_exchange_market.quote_precision
        )

    def get_exchange_balances(self):
        # How much volume can I buy with my payment currency
        self.ask_quote_exchange_qty = self.ask.exchange.get_balance(
            symbol=self.quote_coin
        )
        if self.min_quote_qty > self.ask_quote_exchange_qty:
            msg = NotEnoughBalance(
                self.quote_coin, self.ask.exchange_id, self.ask_quote_exchange_qty
            )
            self.notifier.add(logger, msg)
            return False

        # How much volume can I sell due to how much I have in balance
        self.bid_base_exchange_qty = self.bid.exchange.get_balance(
            symbol=self.base_coin
        )
        if (
            self.min_base_qty > self.bid_base_exchange_qty
            or self.bid_base_exchange_qty == 0.0
        ):
            msg = NotEnoughBalance(
                self.base_coin, self.bid.exchange_id, self.bid_base_exchange_qty
            )
            self.notifier.add(logger, msg)
            return False

        msg = ExchangeBalance(
            self.bid_base_exchange_qty,
            self.base_coin,
            self.bid.exchange_id,
            self.ask_quote_exchange_qty,
            self.quote_coin,
            self.ask.exchange_id,
        )
        self.notifier.add(logger, msg)

        return True

    def get_best_opportunity(self):
        # Get the total order we can make while there is still arbitrage
        self.ask.calculate_opportunity(self.bid.first_price_with_fee)
        self.bid.calculate_opportunity(self.ask.first_price_with_fee)

        # Need to recalculate the quantity based on the result of the lowest exchange/balance
        if self.ask.base_qty > self.bid.base_qty:
            # The bid exchange is dictating the maximum amount, recalculating the ask exchange using the new qty
            self.notifier.add(
                logger, TakingQuantityFrom("BID", self.bid.base_qty, self.base_coin)
            )
            self.ask.calculate_opportunity(
                self.bid.first_price, max_base_qty=self.bid.base_qty
            )

        elif self.bid.base_qty > self.ask.base_qty:
            # The ask exchange is dictating the maximum amount, recalculating the bid exchange using the new qty
            self.notifier.add(
                logger, TakingQuantityFrom("ASK", self.ask.base_qty, self.base_coin)
            )
            self.bid.calculate_opportunity(
                self.ask.first_price, max_base_qty=self.ask.base_qty
            )

        # The BID exchange is where we care about the base qty
        self.bid_base_order_qty = round_down(self.bid.base_qty, self.base_precision)
        # The ASK exchange is where we care about the quote qty
        self.ask_quote_order_qty = round_down(self.ask.quote_qty, self.quote_precision)

    def verify_arbitrage_and_profit(self):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if self.ask.exchange_id == self.bid.exchange_id:
            self.notifier.add(logger, ArbitrageSameExchange())
            return False

        # If these lists are empty then there is no arbitrage
        if not self.ask.opportunity_found or not self.bid.opportunity_found:
            self.notifier.add(logger, NoArbitrage())
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.bid_base_order_qty <= self.min_base_qty:
            self.notifier.add(
                logger,
                BelowMinimalQty(
                    self.base_coin, self.bid_base_order_qty, self.min_base_qty
                ),
            )
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.ask_quote_order_qty <= self.min_quote_qty:
            self.notifier.add(
                logger,
                BelowMinimalQty(
                    self.quote_coin, self.ask_quote_order_qty, self.min_quote_qty
                ),
            )
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit()
        if not adequate_margin:
            return False

        if not self.performance_mode:
            self.notifier.add(logger, self.ask)
            self.notifier.add(logger, self.bid)
            self.notifier.add(
                logger, OrderProfit(profit_perc, self.quote_coin, profit_amount)
            )

        self.expected_profit_perc = profit_perc
        self.expected_profit_amount = profit_amount

        return True

    def adequate_profit(self):
        """
        Return False if we consider the profit margin not large enough
        """
        profit_amount = self.bid.quote_qty - self.ask.quote_qty
        profit_perc = (profit_amount / self.bid.quote_qty) * 100.0

        exchange_profit_perc = self.bid.exchange.min_profit_perc
        min_profit_perc = (
            exchange_profit_perc
            if exchange_profit_perc is not None
            else self.MIN_PROFIT_PERC
        )

        exchange_profit_amount = self.ask.exchange.min_profit_amount
        min_profit_amount = (
            exchange_profit_amount
            if exchange_profit_amount is not None
            else self.MIN_PROFIT_AMOUNT
        )

        adequate_margin_perc = profit_perc >= min_profit_perc
        adequate_margin_amount = profit_amount >= min_profit_amount

        if not adequate_margin_amount and not adequate_margin_perc:
            self.notifier.add(logger, BelowMinProfitPerc(profit_perc, min_profit_perc))
            self.notifier.add(
                logger,
                BelowMinProfitAmount(profit_amount, self.quote_coin, min_profit_amount),
            )

        return (
            (adequate_margin_perc and adequate_margin_amount),
            profit_perc,
            profit_amount,
        )

    def initiate_orders(self):
        self.ordering = True

        # Format prices and qty
        ask_price = rounder(
            self.ask.price, self.ask.exchange_market.price_precision, strip=False
        )
        bid_price = rounder(
            self.bid.price, self.bid.exchange_market.price_precision, strip=False
        )
        quantity = rounder(self.bid_base_order_qty, self.base_precision, strip=False)

        msg = OrderInfo(
            "BUY",
            self.ask.exchange_id,
            quantity,
            ask_price,
            self.ask.price_with_fee,
            self.quote_coin,
        )
        self.notifier.add(logger, msg)

        msg = OrderInfo(
            "SELL",
            self.bid.exchange_id,
            quantity,
            bid_price,
            self.bid.price_with_fee,
            self.quote_coin,
        )
        self.notifier.add(logger, msg)

        if self.simulate:
            return

        loop = asyncio.get_event_loop()
        tasks = [
            self.ask.buy(self.trade_id, quantity, ask_price),
            self.bid.sell(self.trade_id, quantity, bid_price),
        ]
        loop.run_until_complete(asyncio.gather(*tasks))

    def verify_orders(self):
        if self.simulate:
            return

        for i in range(20):
            tasks = [
                order.get_status()
                for order in [self.ask, self.bid]
                if order.status != order.STATUS_FILLED
            ]
            if tasks:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(asyncio.gather(*tasks))
                sleep_now(seconds=1 + (i / 10.0))
            else:
                self.notifier.add(logger, OrderSuccessful())
                self.successful = True

                self.actual_profit_amount = (
                    self.bid.actual_quote_qty - self.ask.actual_quote_qty
                )
                self.actual_profit_perc = (
                    self.actual_profit_amount / self.bid.actual_quote_qty
                ) * 100.0
                return

        self.successful = False
        self.notifier.add(logger, OrderFailed())

    def save_to_database(self, force=False):
        if not force:
            return

        data = {
            "_id": self.trade_id,
            "orders_verified": self.successful,
            "timestamp": self.timestamp,
            "ask_exchange": self.ask.exchange_id,
            "bid_exchange": self.bid.exchange_id,
            "market": self.market,
            "order_quantity": self.bid_base_order_qty,
            "market_pair_id": self.market_pair_id,
            "expected": {
                "ask": {
                    "price": rounder(self.ask.price),
                    "price_with_fee": rounder(self.ask.price_with_fee),
                    "base_quantity": rounder(self.ask.base_qty),
                    "quote_quantity": rounder(self.ask.quote_qty),
                    "order_book": self.ask.order_book,
                    "balance": self.ask.exchange.balance,
                },
                "bid": {
                    "price": rounder(self.bid.price),
                    "price_with_fee": rounder(self.bid.price_with_fee),
                    "base_quantity": rounder(self.bid.base_qty),
                    "quote_quantity": rounder(self.bid.quote_qty),
                    "order_book": self.bid.order_book,
                    "balance": self.bid.exchange.balance,
                },
                "profit_percentage": rounder(self.expected_profit_perc),
                "profit_amount": rounder(self.expected_profit_amount),
            },
            "actual": {
                "ask": {
                    "exchange_order_id": str(self.ask.exchange_order_id),
                    "price": rounder(self.ask.actual_price),
                    "price_with_fee": rounder(self.ask.actual_price_with_fee),
                    "timestamp": self.ask.timestamp,
                    "base_quantity": rounder(self.bid_base_order_qty),
                    "filled": self.ask.status,
                },
                "bid": {
                    "exchange_order_id": str(self.bid.exchange_order_id),
                    "price": rounder(self.bid.actual_price),
                    "price_with_fee": rounder(self.bid.actual_price_with_fee),
                    "timestamp": self.bid.timestamp,
                    "base_quantity": rounder(self.bid_base_order_qty),
                    "filled": self.bid.status,
                },
                "profit_percentage": rounder(self.actual_profit_perc),
                "profit_amount": rounder(self.actual_profit_amount),
            },
        }

        db.client.trades.insert_one(data)
