import asyncio

import datetime
import argparse
import json
import os

from bson import ObjectId

from log import logger_class
from exchanges import initiate_exchanges
from models import db
from utils import sleep_now

LOG_FORMATTER = "[%(levelname)s:%(asctime)s - CRYPTON %(trade_id)s] %(message)s"


class CryptonTrade(object):

    _min_profit_perc = 0.01
    _min_profit_amount = 0.01

    def __init__(
            self,
            market,
            exchanges,
            min_base_qty=None,
            min_quote_qty=None,
            market_pair_id=None,
            simulate=False
    ):
        self.market = market
        self.base_coin, self.quote_coin = market.split("/")

        self.exchanges = exchanges

        self.min_base_qty = min_base_qty
        self.min_quote_qty = min_quote_qty

        self.market_pair_id = market_pair_id or "_".join([*sorted(exchanges), market]).upper()

        self.simulate = simulate

        self.trade_id = ObjectId()
        self.trade_id_logger = {'trade_id': str(self.trade_id)}
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

    def log(self, log_message, level="INFO"):
        if level == "DEBUG":
            logger.debug(log_message, **self.trade_id_logger)
        elif level == "ERROR":
            logger.error(log_message, **self.trade_id_logger)
        else:
            logger.info(log_message, **self.trade_id_logger)

    def start(self):
        self.log('#' * 30)

        # Fetch orders from the exchanges
        success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
        if not success:
            return

        # Find the best ask price and bid price on the two exchanges
        self.determine_ask_and_bid_exchange(best_exchange_asks, best_exchange_bids)

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

    def determine_ask_and_bid_exchange(self, best_exchange_asks, best_exchange_bids):
        # Pick the ask and bid exchange based on arbitrage.
        self.ask = min(best_exchange_asks)
        self.bid = max(best_exchange_bids)
        self.log(self.ask)
        self.log(self.bid)

        # Now ask and bid are known, set the minimal quantity from the exchange if not forced by user
        if self.min_base_qty is None:
            self.min_base_qty = max(
                self.bid.exchange.markets[self.market].min_base_qty,
                self.ask.exchange.markets[self.market].min_base_qty
            )
        if self.min_quote_qty is None:
            self.min_quote_qty = max(
                self.bid.exchange.markets[self.market].min_quote_qty,
                self.ask.exchange.markets[self.market].min_quote_qty
            )

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
            self.log("Taking order quantity from bid quantity: {} {}".format(self.bid.base_qty, self.base_coin))
            self.ask.opportunity(self.bid.first_price_with_fee, max_base_qty=self.bid.base_qty)

        elif self.bid.base_qty > self.ask.base_qty:
            # The ask exchange is dictating the maximum amount, recalculating the bid exchange using the new qty
            self.log("Taking order quantity from ask quantity: {} {}".format(self.ask.base_qty, self.base_coin))
            self.bid.opportunity(self.ask.first_price_with_fee, max_base_qty=self.ask.base_qty)

        # TODO: Check why there is difference:
        """
        TRADE 60d5d0ca3e35a27ae850abbd: ASK(kucoin, MITX/USDT, first_price=0.0382, first_price_with_fee=0.0383, base_qty=10.8329)
        TRADE 60d5d0ca3e35a27ae850abbd: BID(ascendex, MITX/USDT, first_price=0.038486, first_price_with_fee=0.038409, base_qty=941.0)
        TRADE 60d5d0ca3e35a27ae850abbd: 1296.0 MITX on BID exchange ascendex | 131.05260686 USDT on ASK exchange kucoin
        TRADE 60d5d0ca3e35a27ae850abbd: Taking order quantity from ask quantity: 711.3209 MITX
        TRADE 60d5d0ca3e35a27ae850abbd: WHY IS THIS DIFFERENT? 711.3209 711.0
        """
        # # This should always be equal, the base qty never differs, the quote qty does (due to price difference)
        # if self.ask.base_qty != self.bid.base_qty:
        #     self.notify("WHY IS THIS DIFFERENT?", self.ask.base_qty, self.bid.base_qty)
        #     raise ValueError("Stopping because difference in base qty")

        self.bid_base_order_qty = self.bid.base_qty  # The BID exchange is where we care about the base qty
        self.ask_quote_order_qty = self.ask.quote_qty  # The ASK exchange is where we care about the quote qty

    def get_exchange_balances(self):
        msg = "Not enough {} on {}. Current balance: {}"

        # How much volume can I buy with my payment currency
        self.ask_quote_exchange_qty = self.ask.exchange.get_balance(symbol=self.quote_coin)
        if self.min_quote_qty > self.ask_quote_exchange_qty:
            self.log(msg.format(self.quote_coin, self.ask.exchange_id, self.ask_quote_exchange_qty))
            return False

        # How much volume can I sell due to how much I have in balance
        self.bid_base_exchange_qty = self.bid.exchange.get_balance(symbol=self.base_coin)
        if self.min_base_qty > self.bid_base_exchange_qty or self.bid_base_exchange_qty == 0.0:
            self.log(msg.format(self.base_coin, self.bid.exchange_id, self.bid_base_exchange_qty))
            return False

        self.log("{} {} on BID exchange {} | {} {} on ASK exchange {}".format(
            self.bid_base_exchange_qty, self.base_coin, self.bid.exchange_id,
            self.ask_quote_exchange_qty, self.quote_coin, self.ask.exchange_id,
        ))

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
            msg = "Profit percentage {}% below min profit {}%"
            msg = msg.format(round(profit_perc, 8), min_profit_perc)
            self.log(msg)

            msg = "Profit amount {} {} below min profit {} {}"
            msg = msg.format(round(profit_amount, 8), self.quote_coin, min_profit_amount, self.quote_coin)
            self.log(msg)

        return (adequate_margin_perc or adequate_margin_amount), profit_perc, profit_amount

    def verify_arbitrage_and_profit(self):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if self.ask.exchange_id == self.bid.exchange_id:
            self.log("Skipping: Best ask and best bid are on the same exchange")
            return False

        # If these lists are empty then there is no arbitrage
        if not self.ask.opportunity_found or not self.bid.opportunity_found:
            self.log("Skipping: No good arbitrage opportunities found".format(self.min_base_qty))
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.bid_base_order_qty <= self.min_base_qty:
            msg = "Skipping: {} Order quantity {} is below minimal quantity ({})"
            self.log(msg.format(self.base_coin, self.bid_base_order_qty, self.min_base_qty))
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.ask_quote_order_qty <= self.min_quote_qty:
            msg = "Skipping: {} Order quantity {} is below minimal quantity ({})"
            self.log(msg.format(self.quote_coin, self.ask_quote_order_qty, self.min_quote_qty))
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit()
        if not adequate_margin:
            return False

        self.log(self.ask)
        self.log(self.bid)

        # Notify about the profit
        msg = "Profit margin: {}% | Profit in {}: {}"
        self.log(msg.format(round(profit_perc, 8), self.quote_coin, round(profit_amount, 8)))

        self.expected_profit_perc = profit_perc
        self.expected_profit_amount = profit_amount

        return True

    def initiate_orders(self):
        msg = "{} @ {}: quantity={} | price={} | price_with_fee={} {}"
        self.log(msg.format(
            "BUYING ",
            self.ask.exchange_id,
            self.bid_base_order_qty,
            self.ask.price,
            self.ask.price_with_fee,
            self.quote_coin
        ))
        self.log(msg.format(
            "SELLING",
            self.bid.exchange_id,
            self.bid_base_order_qty,
            self.bid.price,
            self.bid.price_with_fee,
            self.quote_coin
        ))

        if self.simulate:
            return

        loop = asyncio.get_event_loop()
        tasks = [
            self.ask.buy(self.trade_id, self.bid_base_order_qty, self.ask.price),
            self.bid.sell(self.trade_id, self.bid_base_order_qty, self.bid.price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

    def cancel_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [self.ask.cancel(), self.bid.cancel()]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        self.ask.exchange.log("Cancelled order {} success: {}".format(self.ask.order_id, response[0]))
        self.bid.exchange.log("Cancelled order {} success: {}".format(self.bid.order_id, response[1]))

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
                self.log("Both orders successful!")
                self.successful = True

                self.actual_profit_amount = self.bid.actual_quote_qty - self.ask.actual_quote_qty
                self.actual_profit_perc = (self.actual_profit_amount / self.bid.actual_quote_qty) * 100.0

                self.ask.exchange.balance[self.quote_coin] -= self.ask_quote_order_qty
                self.bid.exchange.balance[self.base_coin] -= self.bid_base_order_qty
                return

        self.successful = False
        self.log("Something is wrong! Could not verify if orders are successful")


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
    parser.add_argument("-l", "--loglevel", default=False, type=bool, help="debug, info or error")
    args = parser.parse_args()

    logger_class.filename = args.worker
    logger_class.level = args.loglevel
    logger = logger_class.get(__name__, formatter=LOG_FORMATTER)

    settings = load_settings_file(args.worker)
    activate_crypton(settings, simulate=args.simulate)


