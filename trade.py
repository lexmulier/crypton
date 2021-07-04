import asyncio
import logging
import datetime
import argparse
import json
import os

from bson import ObjectId

from log import CryptonLogger
from exchanges import initiate_exchanges
from models import db
from utils import sleep_now, round_and_format, round_down

logger = logging.getLogger(__name__)


class CryptonTrade(object):

    _min_profit_perc = 0.01
    _min_profit_amount = 0.0

    def __init__(
            self,
            market,
            exchanges,
            min_base_qty=None,
            min_quote_qty=None,
            base_precision=None,
            quote_precision=None,
            market_pair_id=None,
            simulate=False,
            log_level=None
    ):
        self.market = market
        self.base_coin, self.quote_coin = market.split("/")

        self.exchanges = exchanges

        self.min_base_qty = min_base_qty
        self.min_quote_qty = min_quote_qty
        self.base_precision = base_precision
        self.quote_precision = quote_precision

        self.market_pair_id = market_pair_id or "_".join([*sorted(exchanges), market]).upper()

        self.simulate = simulate

        self.trade_id = ObjectId()
        self.timestamp = datetime.datetime.now()

        self.successful = None
        self.ask = None
        self.bid = None

        self.bid_base_exchange_qty = 0.0
        self.ask_quote_exchange_qty = 0.0
        self.bid_base_order_qty = 0.0
        self.ask_quote_order_qty = 0.0

        self.expected_profit_perc = None
        self.expected_profit_amount = None
        self.actual_profit_perc = None
        self.actual_profit_amount = None

        if log_level is not None:
            CryptonLogger(level=log_level).initiate()

        self.log = logging.LoggerAdapter(logger, {"module_fields": str(self.trade_id)})

    def start(self):
        self.log.info('#' * 30)

        # Fetch orders from the exchanges
        success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
        if not success:
            return

        # Find the best ask price and bid price on the two exchanges
        self.determine_ask_and_bid_exchange(best_exchange_asks, best_exchange_bids)
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

        # Place the orders
        self.initiate_orders()

        # Check if orders have been filled successfully
        self.verify_orders()

        # Save full order information to the MongoDB database
        self.save_to_database(force=True)

    def determine_min_qty_and_precision(self):
        # Now ask and bid are known, set the minimal quantity and precision from the exchange if not forced by user
        ask_exchange_market = self.ask.exchange.markets[self.market]
        bid_exchange_market = self.bid.exchange.markets[self.market]

        if self.min_base_qty is None:
            self.min_base_qty = max(ask_exchange_market.min_base_qty, bid_exchange_market.min_base_qty)
        if self.min_quote_qty is None:
            self.min_quote_qty = max(ask_exchange_market.min_quote_qty, bid_exchange_market.min_quote_qty)

        if self.base_precision is None:
            self.base_precision = min(ask_exchange_market.base_precision, bid_exchange_market.base_precision)
        if self.quote_precision is None:
            self.quote_precision = min(ask_exchange_market.quote_precision, bid_exchange_market.quote_precision)

    def determine_ask_and_bid_exchange(self, best_exchange_asks, best_exchange_bids):
        # Pick the ask and bid exchange based on arbitrage.
        self.ask = min(best_exchange_asks)
        self.bid = max(best_exchange_bids)

        self.log.info(self.ask)
        self.log.info(self.bid)

    def fetch_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [exchange.markets[self.market].get_orders() for exchange in self.exchanges.values()]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        success_exchange1, best_ask_exchange1, best_bid_exchange1 = response[0]
        success_exchange2, best_ask_exchange2, best_bid_exchange2 = response[1]

        success = success_exchange1 and success_exchange2
        best_exchange_asks = [best_ask_exchange1, best_ask_exchange2]
        best_exchange_bids = [best_bid_exchange1, best_bid_exchange2]

        return success, best_exchange_asks, best_exchange_bids

    def get_best_opportunity(self):
        # Get the total order we can make while there is still arbitrage
        self.ask.opportunity(self.bid.first_price_with_fee, max_quote_qty=self.ask_quote_exchange_qty)
        self.bid.opportunity(self.ask.first_price_with_fee, max_base_qty=self.bid_base_exchange_qty)

        # Need to recalculate the quantity based on the result of the lowest exchange/balance
        if self.ask.base_qty > self.bid.base_qty:
            # The bid exchange is dictating the maximum amount, recalculating the ask exchange using the new qty
            self.log.info(f"Taking order quantity from bid quantity: {self.bid.base_qty:.10f} {self.base_coin}")
            self.ask.opportunity(self.bid.first_price_with_fee, max_base_qty=self.bid.base_qty)

        elif self.bid.base_qty > self.ask.base_qty:
            # The ask exchange is dictating the maximum amount, recalculating the bid exchange using the new qty
            self.log.info(f"Taking order quantity from ask quantity: {self.ask.base_qty:.10f} {self.base_coin}")
            self.bid.opportunity(self.ask.first_price_with_fee, max_base_qty=self.ask.base_qty)

        # The BID exchange is where we care about the base qty
        self.bid_base_order_qty = round_down(self.bid.base_qty, self.base_precision)
        # The ASK exchange is where we care about the quote qty
        self.ask_quote_order_qty = round_down(self.ask.quote_qty, self.quote_precision)

    def get_exchange_balances(self):
        # How much volume can I buy with my payment currency
        self.ask_quote_exchange_qty = self.ask.exchange.get_balance(symbol=self.quote_coin)
        if self.min_quote_qty > self.ask_quote_exchange_qty:
            self.log.info(f"Not enough {self.quote_coin} on {self.ask.exchange_id}. "
                          f"Current balance: {self.ask_quote_exchange_qty:.10f}")
            return False

        # How much volume can I sell due to how much I have in balance
        self.bid_base_exchange_qty = self.bid.exchange.get_balance(symbol=self.base_coin)
        if self.min_base_qty > self.bid_base_exchange_qty or self.bid_base_exchange_qty == 0.0:
            self.log.info(f"Not enough {self.base_coin} on {self.bid.exchange_id}. "
                          f"Current balance: {self.bid_base_exchange_qty:.10f}")
            return False

        self.log.info(f"{self.bid_base_exchange_qty:.10f} {self.base_coin} on BID exchange {self.bid.exchange_id} | "
                      f"{self.ask_quote_exchange_qty:.10f} {self.quote_coin} on ASK exchange {self.ask.exchange_id}")

        return True

    def adequate_profit(self):
        """
        Return False if we consider the profit margin not large enough
        """
        profit_amount = self.bid.quote_qty - self.ask.quote_qty
        profit_perc = (profit_amount / self.bid.quote_qty) * 100.0

        exchange_profit_perc = self.bid.exchange.min_profit_perc
        min_profit_perc = exchange_profit_perc if exchange_profit_perc is not None else self._min_profit_perc

        exchange_profit_amount = self.ask.exchange.min_profit_amount
        min_profit_amount = exchange_profit_amount if exchange_profit_amount is not None else self._min_profit_amount

        adequate_margin_perc = profit_perc >= min_profit_perc
        adequate_margin_amount = profit_amount >= min_profit_amount

        if not adequate_margin_amount and not adequate_margin_perc:
            self.log.info(f"Profit percentage {round_and_format(profit_perc, 8)}% below min profit {min_profit_perc}%")
            self.log.info(f"Profit amount {round_and_format(profit_amount, 8)} {self.quote_coin} below min profit"
                          f" {min_profit_amount} {self.quote_coin}")

        return (adequate_margin_perc or adequate_margin_amount), profit_perc, profit_amount

    def verify_arbitrage_and_profit(self):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if self.ask.exchange_id == self.bid.exchange_id:
            self.log.info("Skipping: Best ask and best bid are on the same exchange")
            return False

        # If these lists are empty then there is no arbitrage
        if not self.ask.opportunity_found or not self.bid.opportunity_found:
            self.log.info("Skipping: No good arbitrage opportunities found")
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.bid_base_order_qty <= self.min_base_qty:
            self.log.info(f"Skipping: {self.base_coin} Order quantity {self.bid_base_order_qty:.10f} "
                          f"is below minimal quantity ({self.min_base_qty})")
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.ask_quote_order_qty <= self.min_quote_qty:
            self.log.info(f"Skipping: {self.quote_coin} Order quantity {self.ask_quote_order_qty:.10f} "
                          f"is below minimal quantity ({self.min_quote_qty})")
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit()
        if not adequate_margin:
            return False

        self.log.info(self.ask)
        self.log.info(self.bid)

        # Notify about the profit
        self.log.info(f"Profit margin: {round_and_format(profit_perc, 15)}% | "
                      f"Profit in {self.quote_coin}: {round_and_format(profit_amount, 15)}")

        self.expected_profit_perc = profit_perc
        self.expected_profit_amount = profit_amount

        return True

    def initiate_orders(self):
        # Format prices and qty
        ask_price = round_and_format(self.ask.price, self.ask.exchange_market.price_precision)
        bid_price = round_and_format(self.bid.price, self.bid.exchange_market.price_precision)
        quantity = round_and_format(self.bid_base_order_qty, self.base_precision)

        if self.simulate:
            return

        loop = asyncio.get_event_loop()
        tasks = [
            self.ask.buy(self.trade_id, quantity, ask_price),
            self.bid.sell(self.trade_id, quantity, bid_price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        ask_price_with_fee = round_and_format(self.ask.price_with_fee, 10)
        bid_price_with_fee = round_and_format(self.bid.price_with_fee, 10)

        self.log.info(f"BUY @ {self.ask.exchange_id}: quantity={quantity} | "
                      f"price={ask_price} | price_with_fee={ask_price_with_fee} {self.quote_coin}")
        self.log.info(f"SELL @ {self.bid.exchange_id}: quantity={quantity} | "
                      f"price={bid_price} | price_with_fee={bid_price_with_fee} {self.quote_coin}")

    def cancel_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [self.ask.cancel(), self.bid.cancel()]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        self.ask.exchange.log.info(f"Cancelled order {self.ask.order_id} success: {response[0]}")
        self.bid.exchange.log.info(f"Cancelled order {self.bid.order_id} success: {response[1]}")

        return response[0] and response[1]

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
                    "price": self.ask.price,
                    "price_with_fee": self.ask.price_with_fee,
                    "base_quantity": self.ask.base_qty,
                    "quote_quantity": self.ask.quote_qty,
                    "order_book": self.ask.order_book,
                    "balance": self.ask.exchange.balance
                },
                "bid": {
                    "price": self.bid.price,
                    "price_with_fee": self.bid.price_with_fee,
                    "base_quantity": self.bid.base_qty,
                    "quote_quantity": self.bid.quote_qty,
                    "order_book": self.bid.order_book,
                    "balance": self.bid.exchange.balance
                },
                "profit_percentage": self.expected_profit_perc,
                "profit_amount": self.expected_profit_amount,
            },
            "actual": {
                "ask": {
                    "exchange_order_id": str(self.ask.exchange_order_id),
                    "price": self.ask.actual_price,
                    "price_with_fee": self.ask.actual_price_with_fee,
                    "timestamp": self.ask.timestamp,
                    "base_quantity": self.bid_base_order_qty,
                    "filled": self.ask.status
                },
                "bid": {
                    "exchange_order_id": str(self.bid.exchange_order_id),
                    "price": self.bid.actual_price,
                    "price_with_fee": self.bid.actual_price_with_fee,
                    "timestamp": self.bid.timestamp,
                    "base_quantity": self.bid_base_order_qty,
                    "filled": self.bid.status
                },
                "profit_percentage": self.actual_profit_perc,
                "profit_amount": self.actual_profit_amount,
            }
        }

        db.client.trades.insert_one(data)

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
                self.log.info("Both orders successful!")
                self.successful = True

                self.actual_profit_amount = self.bid.actual_quote_qty - self.ask.actual_quote_qty
                self.actual_profit_perc = (self.actual_profit_amount / self.bid.actual_quote_qty) * 100.0

                self.ask.exchange.balance[self.quote_coin] -= self.ask_quote_order_qty
                self.bid.exchange.balance[self.base_coin] -= self.bid_base_order_qty
                return

        self.successful = False
        self.log.info("Something is wrong! Could not verify if orders are successful")


def refresh_exchange_balances(counter, exchanges):
    if counter % 200 == 0:
        update_local_balances_from_exchanges(exchanges)
    elif counter % 20 == 0:
        for exchange in exchanges.values():
            exchange.get_balance(from_database=True)


def update_local_balances_from_exchanges(exchanges):
    loop = asyncio.get_event_loop()
    tasks = [exchange.retrieve_balance() for exchange in exchanges.values()]
    loop.run_until_complete(asyncio.gather(*tasks))


def upsert_market_pair(market, exchange_ids):
    market_pair_id = "_".join([*sorted(exchange_ids), market]).upper()
    timestamp = datetime.datetime.now()
    market_pair_info = {
        "market_pair_id": market_pair_id,
        "exchanges": exchange_ids,
        "market": market,
        "last_run": timestamp
    }
    db.client.market_pairs.update_one(
        {"market_pair_id": market_pair_id},
        {"$set": market_pair_info, "$setOnInsert": {"first_run": timestamp}},
        upsert=True
    )
    return market_pair_id


def activate_crypton(settings, simulate=False):
    market_pair_id = upsert_market_pair(
        settings["market"],
        settings["exchanges"]
    )

    exchanges = initiate_exchanges(
        settings["exchanges"],
        preload_market=settings.get("market"),
        exchange_settings=settings["settings"]
    )

    counter = 0
    while True:

        # Refresh balance from the database and sometimes from the exchange
        refresh_exchange_balances(counter, exchanges)

        # Sleep to avoid a API overload
        if settings.get("sleep_time") is not None:
            sleep_now(seconds=settings["sleep_time"])

        # Check and execute trade if there is an opportunity
        trade = CryptonTrade(
            market=settings["market"],
            exchanges=exchanges,
            market_pair_id=market_pair_id,
            min_base_qty=settings.get("min_base_qty"),
            min_quote_qty=settings.get("min_quote_qty"),
            base_precision=settings.get("base_precision"),
            quote_precision=settings.get("quote_precision"),
            simulate=simulate
        )
        trade.start()

        # Update the balance information with the latest from the exchange
        if trade.successful is not None:
            sleep_now(seconds=2)
            update_local_balances_from_exchanges(exchanges)

        counter += 1


def load_settings_file(worker):
    filename = worker if worker[-4:] == "json" else worker + ".json"
    filename = os.path.join("workers", filename)

    if filename is None or not os.path.exists(filename):
        raise ImportError("No settings file is provided or file does not exist!")

    config_file = open(filename).read()
    settings = json.loads(config_file)

    return settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-w", "--worker", type=str, help="Specify the configuration file of the worker")
    parser.add_argument("-s", "--simulate", default=False, type=bool, help="Simulate mode will not order")
    parser.add_argument("-l", "--loglevel", default="INFO", type=str, help="debug, info or error")
    args = parser.parse_args()

    CryptonLogger(filename=args.worker, level=args.loglevel).initiate()

    settings = load_settings_file(args.worker)
    activate_crypton(settings, simulate=args.simulate)


