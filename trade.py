import asyncio

from aiohttp import ClientSession
from bson import ObjectId

from bot import Crypton
from config import *

EXCHANGE_CONFIGS = {
    "binance": BINANCE_CONFIG,
    #"kraken": KRAKEN_CONFIG,
    #"kucoin": KUCOIN_CONFIG,
    "latoken": LATOKEN_CONFIG
}


class CryptonTrade(Crypton):

    MIN_PROFIT_PERCENTAGE = 1.5

    def __init__(self, market, exchange_configs, *args, **kwargs):
        self.market = market
        super(CryptonTrade, self).__init__(exchange_configs, *args, **kwargs)

        self.trade_id = None

    def notify(self, *args):
        if self.verbose:
            print("TRADE {}:".format(self.trade_id if self.trade_id else ""), *args)

    def start(self, min_qty=0):
        while True:
            self.sleep()

            self.notify("#" * 20)
            self.trade_id = ObjectId()

            success, best_exchange_asks, best_exchange_bids = self.fetch_orders(self.market)
            if not success:
                continue

            # Find the best opportunity based on ask/bid price, ask/bid quantity and available funds
            order_qty, best_ask, best_bid = self.get_best_opportunity(best_exchange_asks, best_exchange_bids, min_qty)
            if order_qty <= 0.0:
                continue

            # Check if there is arbitrage and adequate profit
            if not self.verify_arbitrage_and_profit(best_ask, best_bid, order_qty, min_qty):
                continue

            self.notify("Order quantity:", order_qty)

            self.initiate_order(best_ask, best_bid, order_qty)

            break  # Temporary

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

        order_quantity = min(best_ask.best_quantity, best_bid.best_quantity)

        if order_quantity <= 0.0:
            self.notify("No good opportunity")

        return order_quantity, best_ask, best_bid

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

    def fetch_orders(self, market_symbol):
        loop = asyncio.get_event_loop()
        success, best_exchange_asks, best_exchange_bids = loop.run_until_complete(self._fetch_orders(market_symbol))
        return success, best_exchange_asks, best_exchange_bids

    async def _fetch_orders(self, market_symbol):
        tasks = [exchange.markets[market_symbol].get_order() for exchange in self.exchanges.values()]
        exchange1, exchange2 = await asyncio.gather(*tasks, return_exceptions=True)

        success = exchange1[0] and exchange2[0]
        best_exchange_asks = [exchange1[1], exchange2[1]]
        best_exchange_bids = [exchange1[2], exchange2[2]]

        return success, best_exchange_asks, best_exchange_bids

    @staticmethod
    def get_exchange_balances(best_ask, best_bid):
        # How much volume can I buy with my payment currency (we need to calculate it)
        quote_currency = best_ask.exchange_market.quote_coin
        quote_currency_balance = best_ask.exchange.get_balance_fake(quote_currency)  # TODO: Replace function
        ask_exchange_qty = quote_currency_balance / best_ask.price_with_fee

        # How much volume can I sell due to how much I have in balance
        base_currency = best_bid.exchange_market.base_coin
        bid_exchange_qty = best_bid.exchange.get_balance_fake(base_currency)  # TODO: Replace function

        return ask_exchange_qty, bid_exchange_qty

    def adequate_profit(self, best_ask, best_bid):
        """
        Return False if we consider the profit margin not large enough
        """
        bid_price = best_bid.best_price_with_fee
        ask_price = best_ask.best_price_with_fee

        profit_percentage = ((bid_price - ask_price) / ask_price) * 100.0
        percentage_margin = profit_percentage >= self.MIN_PROFIT_PERCENTAGE

        if not percentage_margin:
            msg = "Profit percentage {}% below min profit {}%"
            msg = msg.format(profit_percentage, self.MIN_PROFIT_PERCENTAGE)
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

    def initiate_order(self, best_ask, best_bid, order_qty):
        msg = "{} {} on {} for {} each"
        self.notify(msg.format("Selling", order_qty, best_bid.exchange_id, best_bid.best_price_with_fee))
        self.notify(msg.format("Buying", order_qty, best_ask.exchange_id, best_ask.best_price_with_fee))

        bid_price = best_bid.best_price_with_fee
        ask_price = best_ask.best_price_with_fee

        profit_percentage = ((bid_price - ask_price) / ask_price) * 100.0
        self.notify("Estimated profit {} {}".format(profit_percentage, best_bid.exchange_market.base_coin))

        # WIP

