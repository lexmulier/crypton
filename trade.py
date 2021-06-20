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
            verbose=True
    ):
        self.market = market
        self.base_coin, self.quote_coin = market.split("/")

        self.exchanges = exchanges
        self.min_profit_perc = min_profit_perc if min_profit_perc is not None else self._min_profit_perc
        self.min_profit_amount = min_profit_amount if min_profit_amount is not None else self._min_profit_amount
        self.min_base_qty = min_base_qty if min_base_qty is not None else 0.0
        self.min_quote_qty = min_quote_qty if min_quote_qty is not None else 0.0
        self.verbose = verbose

        self.trade_id = ObjectId()
        self.timestamp = datetime.datetime.now()

        self.successful = None
        self.best_ask = None
        self.best_bid = None
        self.order_qty = 0.0

        self.expected_profit_perc = None
        self.expected_profit_amount = None
        self.actual_profit_perc = None
        self.actual_profit_amount = None

    def notify(self, *args):
        if self.verbose:
            print("TRADE {}:".format(self.trade_id if self.trade_id else ""), *args)

    def start(self):
        self.notify('#' * 30)

        # Fetch orders from the exchanges
        success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
        if not success:
            return

        # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
        self.get_best_opportunity(best_exchange_asks, best_exchange_bids)

        # Check if there is arbitrage and adequate profit
        if not self.verify_arbitrage_and_profit():
            return

        # Place the orders
        self.initiate_orders()

        # Check if orders have been filled successfully
        self.verify_orders()

        # Save full order information to the MongoDB database
        self.save_to_database()

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

    def get_best_opportunity(self, best_exchange_asks, best_exchange_bids):
        self.best_ask = min(best_exchange_asks)
        self.best_bid = max(best_exchange_bids)

        # Get the balance on the exchanges
        exchange_order_qty = self.get_exchange_balances(self.best_ask, self.best_bid)

        # Filter the opportunities based on arbitrage and qty in exchanges
        self.best_ask.opportunity(
            self.best_bid.first_price_with_fee,
            exchange_order_qty,
            self.min_base_qty,
            self.min_quote_qty
        )
        self.best_bid.opportunity(
            self.best_ask.first_price_with_fee,
            exchange_order_qty,
            self.min_base_qty,
            self.min_quote_qty
        )

        # Which quantity is dictating how much we're buying? Best off on ask, bid or balance on exchanges?
        self.order_qty = min(self.best_ask.best_quantity, self.best_bid.best_quantity, exchange_order_qty)

        # If these are equal then quantity is from the exchanges and we don't need recalculation
        if self.order_qty == exchange_order_qty:
            self.notify("Taking order quantity from exchange balance")

        # If best ask quantity is above best bid quantity then we find new best opportunity for best ask
        elif self.best_ask.best_quantity >= self.best_bid.best_quantity:
            self.notify("Taking order quantity from best bid quantity")
            self.best_ask.opportunity(
                self.best_bid.first_price_with_fee,
                self.best_bid.best_quantity,
                self.min_base_qty,
                self.min_quote_qty
            )

        # If best bid quantity is above best ask quantity then we find new best opportunity for best bid
        elif self.best_bid.best_quantity >= self.best_ask.best_quantity:
            self.notify("Taking order quantity from best ask quantity")
            self.best_bid.opportunity(
                self.best_ask.first_price_with_fee,
                self.best_ask.best_quantity,
                self.min_base_qty,
                self.min_quote_qty
            )

        self.notify(self.best_ask)
        self.notify(self.best_bid)

    def get_exchange_balances(self, best_ask, best_bid):
        # How much volume can I buy with my payment currency (we need to calculate it)
        quote_currency = best_ask.exchange_market.quote_coin
        quote_currency_balance = best_ask.exchange.get_balance(symbol=quote_currency)
        ask_exchange_qty = quote_currency_balance / best_ask.first_price_with_fee

        # How much volume can I sell due to how much I have in balance
        base_currency = best_bid.exchange_market.base_coin
        bid_exchange_qty = best_bid.exchange.get_balance(symbol=base_currency)

        # Check if we have enough on balance to proceed on both exchanges (not stopping)
        self.check_enough_balance(best_ask, best_bid, ask_exchange_qty, bid_exchange_qty)

        return min(ask_exchange_qty, bid_exchange_qty)

    def check_enough_balance(self, best_ask, best_bid, ask_exchange_qty, bid_exchange_qty):
        if self.min_base_qty >= bid_exchange_qty:
            self.notify(
                "Not enough {} on {}. Current balance: {}".format(
                    best_bid.exchange_market.base_coin,
                    best_bid.exchange_id,
                    bid_exchange_qty
                )
            )
        elif self.min_base_qty >= ask_exchange_qty:
            self.notify(
                "Not enough {} on {}. Current balance: {}".format(
                    best_ask.exchange_market.quote_coin,
                    best_ask.exchange_id,
                    ask_exchange_qty
                )
            )

    def adequate_profit(self):
        """
        Return False if we consider the profit margin not large enough
        """
        bid_price = self.best_bid.best_price_with_fee
        ask_price = self.best_ask.best_price_with_fee

        profit_perc = ((bid_price - ask_price) / ask_price) * 100.0
        adequate_margin_perc = profit_perc >= self.min_profit_perc

        profit_amount = self.best_bid.best_offer - self.best_ask.best_offer
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
        if self.best_ask.exchange_id == self.best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return False

        # We want to order at least a certain amount to avoid small trading
        if self.order_qty <= self.min_base_qty:
            self.notify("Skipping: Order quantity is below minimal quantity ({})".format(self.min_base_qty))
            return False

        # Check if there is arbitrage because the ask price is higher than the bid price
        if self.best_ask > self.best_bid:
            self.notify("Skipping: Asking price is higher than bid price")
            return False

        # If these lists are empty then there is no arbitrage
        if not self.best_ask.opportunities or not self.best_bid.opportunities:
            self.notify("Skipping: No good arbitrage opportunities found".format(self.min_base_qty))
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit()
        if not adequate_margin:
            return False

        # Notify about the profit
        message = "Profit margin: {}% | Profit in {}: {}"
        self.notify(message.format(round(profit_perc, 8), self.quote_coin, round(profit_amount, 8)))

        self.expected_profit_perc = profit_perc
        self.expected_profit_amount = profit_amount

        return True

    def initiate_orders(self):
        msg = "{} @ {}: quantity={} | price={} {}"
        self.notify(msg.format(
            "BUYING ", self.best_ask.exchange_id, self.order_qty, self.best_ask.best_price, self.quote_coin
        ))
        self.notify(msg.format(
            "SELLING", self.best_bid.exchange_id, self.order_qty, self.best_bid.best_price, self.quote_coin
        ))

        loop = asyncio.get_event_loop()
        tasks = [
            self.best_ask.buy(self.trade_id, self.order_qty, self.best_ask.best_price),
            self.best_bid.sell(self.trade_id, self.order_qty, self.best_bid.best_price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        buy_order_success = response[0]
        sell_order_success = response[1]

        if not any([sell_order_success, buy_order_success]):
            msg = "Error! Trying to cancel both (sell: {}, buy: {})"
            self.notify(msg.format(self.best_bid.order_id, self.best_ask.order_id))
            self.cancel_orders()
            raise ValueError("Order placement was not successful")

    def cancel_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [self.best_ask.cancel(), self.best_bid.cancel()]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        self.best_ask.exchange.notify("Cancelled order {} success: {}".format(self.best_ask.order_id, response[0]))
        self.best_bid.exchange.notify("Cancelled order {} success: {}".format(self.best_bid.order_id, response[1]))

        return response[0] and response[1]

    def save_to_database(self):
        data = {
            "_id": self.trade_id,
            "orders_verified": self.successful,
            "timestamp": self.timestamp,
            "ask_exchange": self.best_ask.exchange_id,
            "bid_exchange": self.best_bid.exchange_id,
            "market": self.market,
            "expected": {
                "ask": {
                    "price": self.best_ask.best_price,
                    "price_with_fee": self.best_ask.best_price_with_fee,
                    "quantity": self.best_ask.best_quantity,
                    "opportunities": self.best_ask.opportunities,
                    "asks": self.best_ask.asks,
                },
                "bid": {
                    "price": self.best_bid.best_price,
                    "price_with_fee": self.best_bid.best_price_with_fee,
                    "quantity": self.best_bid.best_quantity,
                    "opportunities": self.best_bid.opportunities,
                    "bids": self.best_bid.bids,
                },
                "profit_percentage": self.expected_profit_perc,
                "profit_amount": self.expected_profit_amount,
            },
            "actual": {
                "ask": {
                    "exchange_order_id": str(self.best_ask.exchange_order_id),
                    "price": self.best_ask.actual_price,
                    "price_with_fee": self.best_ask.actual_price_with_fee,
                    "timestamp": self.best_ask.timestamp,
                    "filled": self.best_ask.status
                },
                "bid": {
                    "exchange_order_id": str(self.best_bid.exchange_order_id),
                    "price": self.best_bid.actual_price,
                    "price_with_fee": self.best_bid.actual_price_with_fee,
                    "timestamp": self.best_bid.timestamp,
                    "filled": self.best_bid.status
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
                for order in [self.best_ask, self.best_bid]
                if order.status != order.STATUS_FILLED
            ]
            if tasks:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(asyncio.gather(*tasks))
                sleep_now(seconds=1 + (i / 10.0))
            else:
                self.notify("Both orders successful!")
                self.successful = True

                bid_price = self.best_bid.actual_price_with_fee
                ask_price = self.best_ask.actual_price_with_fee
                self.actual_profit_perc = ((bid_price - ask_price) / ask_price) * 100.0
                self.actual_profit_amount = self.best_bid.best_offer - self.best_ask.best_offer
                return

        self.successful = False
        self.notify("Something is wrong! Could not verify if orders are successful")


def refresh_exchange_balances_from_database(counter, exchanges):
    if counter % 20 == 0:
        for exchange in exchanges.values():
            exchange.get_balance(from_database=True)


def update_local_balances_from_exchanges(exchanges):
    loop = asyncio.get_event_loop()
    tasks = [exchange.retrieve_balance() for exchange in exchanges.values()]
    loop.run_until_complete(asyncio.gather(*tasks))


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
    exchanges = initiate_exchanges(exchange_ids, preload_market=market, verbose=verbose)

    counter = 0
    while True:
        counter += 1

        # Refresh balance from the database
        refresh_exchange_balances_from_database(counter, exchanges)

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
            verbose=verbose
        )
        trade.start()

        # Update the balance information with the latest from the exchange
        update_local_balances_from_exchanges(exchanges)


if __name__ == "__main__":
    market = "MITX/USDT"
    exchange_ids = ["ascendex", "kucoin"]
    activate_crypton(market, exchange_ids, min_quote_qty=5.0, sleep_time=0.5, verbose=True)


