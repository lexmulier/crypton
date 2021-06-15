import asyncio
import datetime

from bson import ObjectId

from base import Crypton
from config import *


class CryptonTrade(Crypton):

    MIN_PROFIT_PERCENTAGE = 0.5

    def __init__(
            self,
            market,
            exchange_configs,
            min_profit=None,
            sleep=False,
            *args,
            **kwargs
    ):

        if len(exchange_configs) < 2:
            raise ValueError("You need at least two exchanges to compare arbitrage")

        self.market = market
        self.sleep = sleep
        self.min_profit = min_profit if min_profit is not None else self.MIN_PROFIT_PERCENTAGE
        super(CryptonTrade, self).__init__(exchange_configs, *args, **kwargs)

        self.trade_id = None

    def notify(self, *args):
        if self.verbose:
            print("TRADE {}:".format(self.trade_id if self.trade_id else ""), *args)

    def start(self, min_qty=0):
        while True:
            self.sleep_now()

            self.trade_id = ObjectId()
            self.notify("#" * 20)

            success, best_exchange_asks, best_exchange_bids = self.fetch_orders()
            if not success:
                continue

            # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
            order_qty, best_ask, best_bid = self.get_best_opportunity(best_exchange_asks, best_exchange_bids, min_qty)

            # Check if there is arbitrage and adequate profit
            if not self.verify_arbitrage_and_profit(best_ask, best_bid, order_qty, min_qty):
                continue

            success, sell_order_id, buy_order_id = self.initiate_orders(best_ask, best_bid, order_qty)

            # Check if orders are succesfull

            # Save trade to database

            # Fetch balance again

            break  # Temporary

    def fetch_orders(self):
        loop = asyncio.get_event_loop()
        tasks = [exchange.markets[self.market].get_order() for exchange in self.exchanges.values()]
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
        ask_exchange_qty, bid_exchange_qty = self.get_exchange_balances(best_ask, best_bid)

        # Check if we have enough on balance to proceed on both exchanges (not stopping)
        self.check_enough_balance(best_ask, best_bid, ask_exchange_qty, bid_exchange_qty, min_qty)

        # Filter the opportunities based on arbitrage and qty in exchanges
        best_ask.opportunity(best_bid.price_with_fee, ask_exchange_qty, min_qty)
        best_bid.opportunity(best_ask.price_with_fee, bid_exchange_qty, min_qty)

        self.notify(best_ask)
        self.notify(best_bid)

        order_qty = min(best_ask.best_quantity, best_bid.best_quantity)

        return order_qty, best_ask, best_bid

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
        msg = "{} @ {}: quantity={} | price={}"
        self.notify(msg.format("BUYING ", best_ask.exchange_id, order_qty, best_ask.best_price))
        self.notify(msg.format("SELLING", best_bid.exchange_id, order_qty, best_bid.best_price))
        
        # TRADE 60c7a295e2a82c2313c4fa8c: ####################
        # TRADE 60c7a295e2a82c2313c4fa8c: ASK(kucoin, MITX/USDT, offer=6.617618579519999, price=0.0624, qty=105.8399, first_price=0.0605, first_qty=105.8399)
        # TRADE 60c7a295e2a82c2313c4fa8c: BID(ascendex, MITX/USDT, offer=7.797271199999999, price=0.057502, qty=113.0, first_price=0.057502, first_qty=113.0)
        # TRADE 60c7a295e2a82c2313c4fa8c: Best offer has a profit margin of 10.360049132504223
        # TRADE 60c7a295e2a82c2313c4fa8c: BUYING  @ kucoin: quantity=105.8399 | price=0.0624
        # TRADE 60c7a295e2a82c2313c4fa8c: SELLING @ ascendex: quantity=105.8399 | price=0.057502

        loop = asyncio.get_event_loop()
        tasks = [
            best_ask.exchange_market.buy_order(self.trade_id, order_qty, best_ask.best_price),
            best_bid.exchange_market.sell_order(self.trade_id, order_qty, best_bid.best_price)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        buy_order_success, buy_order_id = response[0]
        sell_order_success, sell_order_id = response[1]

        if not any([sell_order_success, buy_order_success]):
            self.notify("Error! Cancelling both (sell: {}, buy: {})".format(sell_order_id, buy_order_id))
            self.cancel_orders(best_ask, best_bid, sell_order_id, buy_order_id)
            return False, None, None

        return True, sell_order_id, buy_order_id

    @staticmethod
    def cancel_orders(best_ask, best_bid, sell_order_id, buy_order_id):
        loop = asyncio.get_event_loop()
        tasks = [
            best_ask.exchange_market.cancel_order(buy_order_id),
            best_bid.exchange_market.cancel_order(sell_order_id)
        ]
        response = loop.run_until_complete(asyncio.gather(*tasks))

        best_ask.exchange.notify("Cancelled order {} success: {}".format(buy_order_id, response[0][0]))
        best_bid.exchange.notify("Cancelled order {} success: {}".format(sell_order_id, response[1][0]))

        return response[0][0] and response[1][0]

    @staticmethod
    def get_exchange_balances(best_ask, best_bid):
        # How much volume can I buy with my payment currency (we need to calculate it)
        # TODO: Is this what I'm doing correct?
        quote_currency = best_ask.exchange_market.quote_coin
        quote_currency_balance = best_ask.exchange.get_balance(quote_currency)
        ask_exchange_qty = quote_currency_balance / best_ask.price_with_fee

        # How much volume can I sell due to how much I have in balance
        base_currency = best_bid.exchange_market.base_coin
        bid_exchange_qty = best_bid.exchange.get_balance(base_currency)

        # TODO: Temp
        ask_exchange_qty = best_ask.first_quantity
        bid_exchange_qty = best_bid.first_quantity

        return ask_exchange_qty, bid_exchange_qty

    def adequate_profit(self, best_ask, best_bid):
        """
        Return False if we consider the profit margin not large enough
        """
        bid_price = best_bid.best_price_with_fee
        ask_price = best_ask.best_price_with_fee

        profit_percentage = ((bid_price - ask_price) / ask_price) * 100.0
        percentage_margin = profit_percentage >= self.min_profit

        if not percentage_margin:
            msg = "Profit percentage {}% below min profit {}%"
            msg = msg.format(profit_percentage, self.min_profit)
            self.notify(msg)

        self.notify("Best offer has a profit margin of", profit_percentage)

        return percentage_margin

    def verify_arbitrage_and_profit(self, best_ask, best_bid, order_qty, minimal_qty):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """

        # Check if the best ask and best bid are on different exchanges.
        if best_ask.exchange_id == best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return False

        if order_qty <= 0.0:
            self.notify("Skipping: No good opportunity after comparing exchanges offers incl fees.")
            return False

        # Check if the best asking price with fee is lower than the best asking bid with fee
        if best_ask >= best_bid:
            self.notify("Skipping: There is no arbitrage")
            return False

        # We want to order at least a certain amount to avoid small trading
        if order_qty <= minimal_qty:
            self.notify("Skipping: Order quantity is too low (Do we get here ever?)")
            return False

        # Check if the amount or percentage is high enough to take the risk
        if not self.adequate_profit(best_ask, best_bid):
            return False

        return True


if __name__ == "__main__":
    EXCHANGE_CONFIGS = {
        "kucoin": KUCOIN_CONFIG,
        "ascendex": ASCENDEX_CONFIG
    }
    self = CryptonTrade("MITX/USDT", EXCHANGE_CONFIGS, sleep=True, verbose=True)
    self.start()
