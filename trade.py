import asyncio
import datetime

from bson import ObjectId

from base import Crypton
from config import *
from models import db


class CryptonTrade(Crypton):

    MIN_PROFIT_PERCENTAGE = 0.5
    MIN_PROFIT_AMOUNT = 0.5

    def __init__(
            self,
            market,
            exchange_configs,
            min_profit_perc=None,
            min_profit_amount=None,
            sleep=False,
            *args,
            **kwargs
    ):

        if len(exchange_configs) < 2:
            raise ValueError("You need at least two exchanges to compare arbitrage")

        self.market = market
        self.base_coin, self.quote_coin = market.split("/")
        self.sleep = sleep
        self.min_profit_perc = min_profit_perc if min_profit_perc is not None else self.MIN_PROFIT_PERCENTAGE
        self.min_profit_amount = min_profit_amount if min_profit_amount is not None else self.MIN_PROFIT_AMOUNT
        super(CryptonTrade, self).__init__(exchange_configs, *args, **kwargs)

        self.trade_id = None

    def notify(self, *args):
        if self.verbose:
            print("TRADE {}:".format(self.trade_id if self.trade_id else ""), *args)

    def start(self, min_qty=0):
        while True:
            self.sleep_now()

            self.trade_id = ObjectId()
            timestamp = datetime.datetime.now()
            self.notify("#" * 20)

            success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
            if not success:
                continue

            # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
            order_qty, best_ask, best_bid = self.get_best_opportunity(best_exchange_asks, best_exchange_bids, min_qty)

            # Check if there is arbitrage and adequate profit
            if not self.verify_arbitrage_and_profit(best_ask, best_bid, order_qty, min_qty):
                continue

            # Place the orders
            self.initiate_orders(best_ask, best_bid, order_qty)

            # Check if orders have been filled successfully
            orders_successful = self.verify_orders(best_ask, best_bid)

            self.save_to_database(best_ask, best_bid, timestamp, orders_successful)

            # Fetch balance again

            break  # Temporary

    def save_to_database(self, best_ask, best_bid, timestamp, orders_successful):
        data = {
            "_id": self.trade_id,
            "orders_verified": orders_successful,
            "timestamp": timestamp,
            "ask_exchange": best_ask.exchange_id,
            "bid_exchange": best_bid.exchange_id,
            "market": self.market,
            "expected": {
                "ask": {
                    "price": best_ask.best_price,
                    "price_with_fee": best_ask.best_price_with_fee,
                    "quantity": best_ask.best_quantity,
                    "opportunities": best_ask.opportunities,
                    "asks": best_ask.asks,
                },
                "bid": {
                    "price": best_bid.best_price,
                    "price_with_fee": best_bid.best_price_with_fee,
                    "quantity": best_bid.best_quantity,
                    "opportunities": best_bid.opportunities,
                    "bids": best_bid.bids,
                }
            },
            "actual": {
                "ask": {
                    "exchange_order_id": best_ask.exchange_order_id,
                    "price": best_ask.actual_price,
                    "price_with_fee": best_ask.actual_price_with_fee,
                    "timestamp": best_ask.timestamp,
                    "filled": best_ask.status
                },
                "bid": {
                    "exchange_order_id": best_bid.exchange_order_id,
                    "price": best_bid.actual_price,
                    "price_with_fee": best_bid.actual_price_with_fee,
                    "timestamp": best_bid.timestamp,
                    "filled": best_bid.status
                }
            }
        }

        db.client.trades.insert_one(data)

    def verify_orders(self, best_ask, best_bid):

        for i in range(20):
            tasks = [order.get_status() for order in [best_ask, best_bid] if order.status != order.status_success]
            if tasks:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(asyncio.gather(*tasks))
                self.sleep_now(seconds=1)
            else:
                self.notify("Both orders successful!")
                return True

        self.notify("Something is wrong! Could not verify if orders are successful")
        return False

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

    def get_best_opportunity(self, best_exchange_asks, best_exchange_bids, min_qty):
        best_ask = min(best_exchange_asks)
        best_bid = max(best_exchange_bids)

        # Get the balance on the exchanges
        exchange_order_qty = self.get_exchange_balances(best_ask, best_bid, min_qty)

        # Filter the opportunities based on arbitrage and qty in exchanges
        best_ask.opportunity(best_bid.first_price_with_fee, exchange_order_qty, min_qty)
        best_bid.opportunity(best_ask.first_price_with_fee, exchange_order_qty, min_qty)

        # Which quantity is dictating how much we're buying? Best off on ask, bid or balance on exchanges?
        possible_order_qty = min(best_ask.best_quantity, best_bid.best_quantity, exchange_order_qty)

        # If these are equal then quantity is from the exchanges and we don't need recalculation
        if possible_order_qty == exchange_order_qty:
            self.notify("Taking order quantity from exchange balance")

        # If best ask quantity is above best bid quantity then we find new best opportunity for best ask
        elif best_ask.best_quantity >= best_bid.best_quantity:
            self.notify("Taking order quantity from best bid quantity")
            best_ask.opportunity(best_bid.first_price_with_fee, best_bid.best_quantity, min_qty)

        # If best bid quantity is above best ask quantity then we find new best opportunity for best bid
        elif best_bid.best_quantity >= best_ask.best_quantity:
            self.notify("Taking order quantity from best ask quantity")
            best_bid.opportunity(best_ask.first_price_with_fee, best_ask.best_quantity, min_qty)

        self.notify(best_ask)
        self.notify(best_bid)

        return possible_order_qty, best_ask, best_bid

    def check_enough_balance(self, best_ask, best_bid, ask_exchange_qty, bid_exchange_qty, minimal_qty):
        if minimal_qty > bid_exchange_qty:
            self.notify(
                "Not enough {} on {}. Current balance: {}".format(
                    best_bid.exchange_market.base_coin,
                    best_bid.exchange_id,
                    bid_exchange_qty
                )
            )
        elif minimal_qty > ask_exchange_qty:
            self.notify(
                "Not enough {} on {}. Current balance: {}".format(
                    best_ask.exchange_market.quote_coin,
                    best_ask.exchange_id,
                    ask_exchange_qty
                )
            )

    def initiate_orders(self, best_ask, best_bid, order_qty):
        msg = "{} @ {}: quantity={} | price={} {}"
        self.notify(msg.format("BUYING ", best_ask.exchange_id, order_qty, best_ask.best_price, self.quote_coin))
        self.notify(msg.format("SELLING", best_bid.exchange_id, order_qty, best_bid.best_price, self.quote_coin))

        loop = asyncio.get_event_loop()
        tasks = [
            best_ask.buy(self.trade_id, order_qty, best_ask.best_price),
            best_bid.sell(self.trade_id, order_qty, best_bid.best_price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        buy_order_success = response[0][0]
        sell_order_success = response[1][0]

        if not any([sell_order_success, buy_order_success]):
            msg = "Error! Trying to cancel both (sell: {}, buy: {})"
            self.notify(msg.format(best_bid.order_id, best_ask.order_id))
            self.cancel_orders(best_ask, best_bid)
            raise ValueError("Order placement was not successful")

    @staticmethod
    def cancel_orders(best_ask, best_bid):
        loop = asyncio.get_event_loop()
        tasks = [
            best_ask.cancel(),
            best_bid.cancel()
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        best_ask.exchange.notify("Cancelled order {} success: {}".format(best_ask.order_id, response[0][0]))
        best_bid.exchange.notify("Cancelled order {} success: {}".format(best_bid.order_id, response[1][0]))

        return response[0][0] and response[1][0]

    def get_exchange_balances(self, best_ask, best_bid, min_qty):
        # How much volume can I buy with my payment currency (we need to calculate it)
        quote_currency = best_ask.exchange_market.quote_coin
        quote_currency_balance = best_ask.exchange.get_balance(quote_currency)
        ask_exchange_qty = quote_currency_balance / best_ask.first_price_with_fee

        # How much volume can I sell due to how much I have in balance
        base_currency = best_bid.exchange_market.base_coin
        bid_exchange_qty = best_bid.exchange.get_balance(base_currency)

        # TODO: Temp
        ask_exchange_qty = 100000000000000
        bid_exchange_qty = 100000000000000

        # Check if we have enough on balance to proceed on both exchanges (not stopping)
        self.check_enough_balance(best_ask, best_bid, ask_exchange_qty, bid_exchange_qty, min_qty)

        return min(ask_exchange_qty, bid_exchange_qty)

    def adequate_profit(self, best_ask, best_bid):
        """
        Return False if we consider the profit margin not large enough
        """
        bid_price = best_bid.best_price_with_fee
        ask_price = best_ask.best_price_with_fee

        profit_perc = ((bid_price - ask_price) / ask_price) * 100.0
        adequate_margin_perc = profit_perc >= self.min_profit_perc

        if not adequate_margin_perc:
            msg = "Profit percentage {}% below min profit {}%"
            msg = msg.format(profit_perc, self.min_profit_perc)
            self.notify(msg)

        profit_amount = best_bid.best_offer - best_ask.best_offer
        adequate_margin_amount = profit_amount >= self.min_profit_amount

        if not adequate_margin_amount:
            msg = "Profit amount {}% below min profit {}"
            msg = msg.format(profit_amount, self.min_profit_amount)
            self.notify(msg)

        return (adequate_margin_perc and adequate_margin_amount), profit_perc, profit_amount

    def verify_arbitrage_and_profit(self, best_ask, best_bid, order_qty, minimal_qty):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if best_ask.exchange_id == best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return False

        # Check if there is arbitrage because the ask price is higher than the bid price
        if best_ask > best_bid:
            self.notify("Skipping: Asking price is higher than bid price")
            return False

        # If these lists are empty then there is no arbitrage
        if not best_ask.opportunities or not best_bid.opportunities:
            self.notify("Skipping: No good arbitrage opportunities found".format(minimal_qty))
            return False

        # We want to order at least a certain amount to avoid small trading
        if order_qty <= minimal_qty:
            self.notify("Skipping: Order quantity is below minimal quantity ({})".format(minimal_qty))
            return False

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit(best_ask, best_bid)
        if not adequate_margin:
            return False

        # Notify about the profit
        message = "Profit margin: {}% | Profit in {}: {}"
        self.notify(message.format(round(profit_perc, 8), self.quote_coin, round(profit_amount, 8)))

        return True


if __name__ == "__main__":
    EXCHANGE_CONFIGS = {
        "kucoin": KUCOIN_CONFIG,
        "ascendex": ASCENDEX_CONFIG
    }
    bot = CryptonTrade("MITX/USDT", EXCHANGE_CONFIGS, sleep=True, verbose=True)
    bot.start()
