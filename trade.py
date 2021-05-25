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

    MIN_PROFIT_PERCENTAGE = 0.5
    MIN_PROFIT_AMOUNT = 1.0

    def __init__(self, *args, **kwargs):
        super(CryptonTrade, self).__init__(*args, **kwargs)
        self.trade_id = None

    def notify(self, *args):
        if self.verbose:
            if self.trade_id is not None:
                print("TRADE {}:".format(self.trade_id), *args)
            else:
                print(*args)

    def start(self, market_symbol):
        while True:
            self.sleep()
            self.notify("#" * 20)
            self.trade_id = ObjectId()

            success, best_exchange_asks, best_exchange_bids = self.fetch_orders(market_symbol)
            if not success:
                continue

            # Best ask
            best_ask = min(best_exchange_asks)
            self.notify(best_ask)

            # Best bid
            best_bid = max(best_exchange_bids)
            self.notify(best_bid)

            # Calculate the maximum quantity we can purchase based on bid, ask and balances
            order_quantity = self.get_max_quantity(best_ask, best_bid)

            # Check if there is arbitrage and adequate profit
            if not self.verify_arbitrage_and_profit(best_ask, best_bid, order_quantity):
                continue

            self.initiate_order(best_ask, best_bid, order_quantity)

            break  # Temporary

    def fetch_orders(self, market_symbol):
        best_exchange_asks = []
        best_exchange_bids = []
        for exchange in self.exchanges.values():

            self.notify("Pinging {}".format(exchange.exchange_id))

            exchange_market = exchange.markets[market_symbol]
            success, best_ask, best_bid = exchange_market.get_order()

            if success is False:
                self.notify(exchange.exchange_id, "API Failed. We need to retry all Exchanges")
                return False, []

            best_exchange_asks.append(best_ask)
            best_exchange_bids.append(best_bid)

        return True, best_exchange_asks, best_exchange_bids

    def get_max_quantity(self, best_ask, best_bid):
        # How much volume is the lowest ask selling
        best_ask_quantity = best_ask.quantity

        # How much volume is the highest bid buying
        best_bid_quantity = best_bid.quantity

        # How much volume can I buy with my payment currency (we need to calculate it)
        quote_currency = best_ask.exchange_market.quote_coin
        quote_currency_balance = best_ask.exchange.get_balance(quote_currency)
        ask_exchange_quantity = quote_currency_balance / best_ask.price_with_fee
        ask_exchange_quantity = ask_exchange_quantity or best_ask_quantity  # TEMP!!!

        # How much volume can I sell due to how much I have in balance
        base_currency = best_bid.exchange_market.base_coin
        bid_exchange_quantity = best_bid.exchange.get_balance(base_currency) or best_bid_quantity  # TEMP!!!

        # We take the lowest volume as it's our limit
        order_quantity = min(best_ask_quantity, ask_exchange_quantity, best_bid_quantity, bid_exchange_quantity)

        self.notify("Max possible quantity:", order_quantity)

        return order_quantity

    def adequate_profit(self, best_ask, best_bid, order_quantity):
        """
        Return False if we consider the profit margin not large enough
        """
        profit_percentage = (best_bid.price_with_fee - best_ask.price_with_fee) / best_bid.price_with_fee
        percentage_margin = profit_percentage >= self.MIN_PROFIT_PERCENTAGE

        profit_amount = (best_bid.price_with_fee * order_quantity) - (best_ask.price_with_fee * order_quantity)  # TODO: Should fee be included in this calculation?
        amount_margin = profit_amount >= self.MIN_PROFIT_AMOUNT

        if not percentage_margin and not amount_margin:
            msg = "Profit percentage {}% below min profit {}% | Profit amount {} below min profit {}"
            msg = msg.format(profit_percentage, self.MIN_PROFIT_PERCENTAGE, profit_amount, self.MIN_PROFIT_AMOUNT)
            self.notify(msg)

        return percentage_margin or amount_margin

    def verify_arbitrage_and_profit(self, best_ask, best_bid, order_quantity):
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

        if order_quantity <= 0.0:
            self.notify("Skipping: Not enough volume to proceed")
            return False

        # Check if the amount or percentage is high enough to take the risk
        if not self.adequate_profit(best_ask, best_bid, order_quantity):
            return False

        # TODO: Check if we can get more bids to find the highest. Pagination?

        return True

    def initiate_order(self, best_ask, best_bid, order_quantity):
        msg = "{} {} on {} for {} each"
        self.notify(msg.format("Selling", order_quantity, best_bid.exchange_id, best_bid.price_with_fee))
        self.notify(msg.format("Buying", order_quantity, best_ask.exchange_id, best_ask.price_with_fee))

        profit = (best_bid.price_with_fee * order_quantity) - (best_ask.price_with_fee * order_quantity)
        self.notify("Estimated profit {} {}".format(profit, best_bid.exchange_market.base_coin))

        # WIP
