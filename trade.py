import asyncio
import datetime

from bson import ObjectId

from exchanges import initiate_exchanges
from models import db
from utils import sleep_now


class CryptonTrade(object):

    _min_profit_perc = 0.5
    _min_profit_amount = 0.2

    def __init__(
            self,
            market,
            exchanges,
            min_profit_perc=None,
            min_profit_amount=None,
            min_base_qty=None,
            min_quote_qty=None,
            market_pair_id=None,
            verbose=True
    ):
        self.market = market
        self.base_coin, self.quote_coin = market.split("/")

        self.exchanges = exchanges
        self.min_profit_perc = min_profit_perc if min_profit_perc is not None else self._min_profit_perc
        self.min_profit_amount = min_profit_amount if min_profit_amount is not None else self._min_profit_amount
        self.min_base_qty = min_base_qty if min_base_qty is not None else 0.0
        self.min_quote_qty = min_quote_qty if min_quote_qty is not None else 0.0

        market_pair_id = market_pair_id or "_".join([*sorted(exchanges), market])
        self.market_pair_id = market_pair_id.upper()

        self.verbose = verbose

        self.trade_id = ObjectId()
        self.timestamp = datetime.datetime.now()

        self.successful = None
        self.ask = None
        self.bid = None

        self.bid_base_exchange_qty = 0.0
        self.ask_quote_exchange_qty = 0.0
        self.base_order_qty = 0.0
        self.quote_order_qty = 0.0

        self.expected_profit_perc = None
        self.expected_profit_amount = None
        self.actual_profit_perc = None
        self.actual_profit_amount = None

    def notify(self, *args):
        if self.verbose:
            print("TRADE {}:".format(self.trade_id if self.trade_id else ""), *args)

    def start(self, simulate=False):
        self.notify('#' * 30)

        # Fetch orders from the exchanges
        success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
        if not success:
            return

        # Find the best ask price and bid price on the two exchanges
        self.determine_ask_and_bid_exchange(best_exchange_asks, best_exchange_bids)

        # Get the balance on the exchanges
        if not self.get_exchange_balances():
            return

        # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
        self.get_best_opportunity()

        # Check if there is arbitrage and adequate profit
        if not self.verify_arbitrage_and_profit() or simulate:
            return

        # Place the orders
        self.initiate_orders()

        # Check if orders have been filled successfully
        self.verify_orders()

        # Save full order information to the MongoDB database
        self.save_to_database()

    def determine_ask_and_bid_exchange(self, best_exchange_asks, best_exchange_bids):
        self.ask = min(best_exchange_asks)
        self.bid = max(best_exchange_bids)
        self.notify(self.ask)
        self.notify(self.bid)

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
        # Filter the opportunities based on arbitrage and qty in exchanges
        self.ask.opportunity(self.bid.first_price_with_fee, max_quote_qty=self.ask_quote_exchange_qty)
        self.bid.opportunity(self.ask.first_price_with_fee, max_base_qty=self.bid_base_exchange_qty)

        # Need to recalculate the quantity based on the result of the lowest exchange/balance
        if self.ask.base_qty > self.bid.base_qty:
            self.notify("Taking order quantity from best bid quantity")
            self.ask.opportunity(self.bid.first_price_with_fee, max_base_qty=self.bid.base_qty)

        elif self.bid.base_qty > self.ask.base_qty:
            self.notify("Taking order quantity from best ask quantity")
            self.bid.opportunity(self.ask.first_price_with_fee, max_base_qty=self.ask.base_qty)

        assert self.ask.base_qty == self.bid.base_qty

        self.base_order_qty = self.bid.base_qty
        self.quote_order_qty = self.ask.quote_qty

    def get_exchange_balances(self):
        msg = "Not enough {} on {}. Current balance: {}"

        # How much volume can I buy with my payment currency
        self.ask_quote_exchange_qty = self.ask.exchange.get_balance(symbol=self.quote_coin)
        if self.min_quote_qty > self.ask_quote_exchange_qty:
            self.notify(msg.format(self.quote_coin, self.ask.exchange_id, self.ask_quote_exchange_qty))
            return False

        # How much volume can I sell due to how much I have in balance
        self.bid_base_exchange_qty = self.bid.exchange.get_balance(symbol=self.base_coin)
        if self.min_base_qty > self.bid_base_exchange_qty or self.bid_base_exchange_qty == 0.0:
            self.notify(msg.format(self.base_coin, self.bid.exchange_id, self.bid_base_exchange_qty))
            return False

        return True

    def adequate_profit(self):
        """
        Return False if we consider the profit margin not large enough
        """
        profit_amount = self.bid.quote_qty - self.ask.quote_qty
        profit_perc = (profit_amount / self.bid.quote_qty) * 100.0

        adequate_margin_perc = profit_perc >= self.min_profit_perc
        adequate_margin_amount = profit_amount >= self.min_profit_amount

        if not adequate_margin_amount and not adequate_margin_perc:
            msg = "Profit percentage {}% below min profit {}%"
            msg = msg.format(round(profit_perc, 8), self.min_profit_perc)
            self.notify(msg)

            msg = "Profit amount {} {} below min profit {} {}"
            msg = msg.format(round(profit_amount, 8), self.quote_coin, self.min_profit_amount, self.quote_coin)
            self.notify(msg)

        return (adequate_margin_perc or adequate_margin_amount), profit_perc, profit_amount

    def verify_arbitrage_and_profit(self):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if self.ask.exchange_id == self.bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.base_order_qty <= self.min_base_qty:
            msg = "Skipping: {} Order quantity {} is below minimal quantity ({})"
            self.notify(msg.format(self.base_coin, self.base_order_qty, self.min_base_qty))
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.quote_order_qty <= self.min_quote_qty:
            msg = "Skipping: {} Order quantity {} is below minimal quantity ({})"
            self.notify(msg.format(self.quote_coin, self.quote_order_qty, self.min_quote_qty))
            return False

        # Check if there is arbitrage because the ask price is higher than the bid price
        if self.ask > self.bid:
            #TODO: Probably not needed.
            self.notify("Skipping: Asking price is higher than bid price")
            return False

        # If these lists are empty then there is no arbitrage
        if not self.ask.opportunity_found or not self.bid.opportunity_found:
            self.notify("Skipping: No good arbitrage opportunities found".format(self.min_base_qty))
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit()
        if not adequate_margin:
            return False

        self.notify(self.ask)
        self.notify(self.bid)

        # Notify about the profit
        message = "Profit margin: {}% | Profit in {}: {}"
        self.notify(message.format(round(profit_perc, 8), self.quote_coin, round(profit_amount, 8)))

        self.expected_profit_perc = profit_perc
        self.expected_profit_amount = profit_amount

        return True

    def initiate_orders(self):
        msg = "{} @ {}: quantity={} | price={} | price_with_fee={} {}"
        self.notify(msg.format(
            "BUYING ",
            self.ask.exchange_id,
            self.base_order_qty, 
            self.ask.price,
            self.ask.price_with_fee,
            self.quote_coin
        ))
        self.notify(msg.format(
            "SELLING",
            self.bid.exchange_id,
            self.base_order_qty,
            self.bid.price,
            self.bid.price_with_fee,
            self.quote_coin
        ))

        loop = asyncio.get_event_loop()
        tasks = [
            self.ask.buy(self.trade_id, self.base_order_qty, self.ask.price),
            self.bid.sell(self.trade_id, self.base_order_qty, self.bid.price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        buy_order_success = response[0]
        sell_order_success = response[1]

        if not any([sell_order_success, buy_order_success]):
            msg = "Error! Trying to cancel both (sell: {}, buy: {})"
            self.notify(msg.format(self.bid.order_id, self.ask.order_id))
            self.cancel_orders()
            raise ValueError("Order placement was not successful")

    def cancel_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [self.ask.cancel(), self.bid.cancel()]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        self.ask.exchange.notify("Cancelled order {} success: {}".format(self.ask.order_id, response[0]))
        self.bid.exchange.notify("Cancelled order {} success: {}".format(self.bid.order_id, response[1]))

        return response[0] and response[1]

    def save_to_database(self):
        data = {
            "_id": self.trade_id,
            "orders_verified": self.successful,
            "timestamp": self.timestamp,
            "ask_exchange": self.ask.exchange_id,
            "bid_exchange": self.bid.exchange_id,
            "market": self.market,
            "order_quantity": self.base_order_qty,
            "market_pair_id": self.market_pair_id,
            "expected": {
                "ask": {
                    "price": self.ask.price,
                    "price_with_fee": self.ask.price_with_fee,
                    "base_quantity": self.ask.base_qty,
                    "quote_quantity": self.ask.quote_qty,
                    "opportunities": self.ask.opportunities,
                    "asks": self.ask.asks,
                },
                "bid": {
                    "price": self.bid.price,
                    "price_with_fee": self.bid.price_with_fee,
                    "base_quantity": self.bid.base_qty,
                    "quote_quantity": self.bid.quote_qty,
                    "opportunities": self.bid.opportunities,
                    "bids": self.bid.bids,
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
                    "base_quantity": self.base_order_qty,
                    "filled": self.ask.status
                },
                "bid": {
                    "exchange_order_id": str(self.bid.exchange_order_id),
                    "price": self.bid.actual_price,
                    "price_with_fee": self.bid.actual_price_with_fee,
                    "base_quantity": self.base_order_qty,
                    "timestamp": self.bid.timestamp,
                    "filled": self.bid.status
                },
                "profit_percentage": self.actual_profit_perc,
                "profit_amount": self.actual_profit_amount,
            }
        }

        db.client.trades.insert_one(data)

    def verify_orders(self):
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
                self.notify("Both orders successful!")
                self.successful = True

                self.actual_profit_amount = self.bid.actual_quote_qty - self.ask.actual_quote_qty
                self.actual_profit_perc = (self.actual_profit_amount / self.bid.actual_quote_qty) * 100.0
                return

        self.successful = False
        self.notify("Something is wrong! Could not verify if orders are successful")


def refresh_exchange_balances(counter, exchanges):
    if counter % 1000 == 0:
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


def activate_crypton(
        market,
        exchange_ids,
        min_profit_perc=None,
        min_profit_amount=None,
        min_base_qty=0.0,
        min_quote_qty=0.0,
        sleep_time=0.1,
        verbose=False
):
    market_pair_id = upsert_market_pair(market, exchange_ids)
    exchanges = initiate_exchanges(exchange_ids, preload_market=market, verbose=verbose)

    counter = 0
    while True:

        # Refresh balance from the database and sometimes from the exchange
        refresh_exchange_balances(counter, exchanges)

        # Sleep to avoid a API overload
        if sleep_time is not None:
            sleep_now(seconds=sleep_time)

        # Check and execute trade if there is an opportunity
        trade = CryptonTrade(
            market=market,
            exchanges=exchanges,
            min_profit_perc=min_profit_perc,
            min_profit_amount=min_profit_amount,
            min_base_qty=min_base_qty,
            min_quote_qty=min_quote_qty,
            market_pair_id=market_pair_id,
            verbose=verbose
        )
        trade.start()

        # Update the balance information with the latest from the exchange
        if trade.successful is not None:
            sleep_now(seconds=5)
            update_local_balances_from_exchanges(exchanges)

        counter += 1


if __name__ == "__main__":
    market = "MITX/USDT"
    exchange_ids = ["ascendex", "kucoin"]
    activate_crypton(market, exchange_ids, min_quote_qty=5.0, min_base_qty=10.0, verbose=True)


