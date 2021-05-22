from bot import Crypton
from config import KRAKEN_CONFIG, KUCOIN_CONFIG, LATOKEN_CONFIG

EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    "latoken": LATOKEN_CONFIG
}


class CryptonTrade(Crypton):

    DEFAULT_MIN_PROFIT_MARGIN = 0.5
    DEFAULT_MIN_PROFIT_AMOUNT = 10.0

    def __init__(self, *args, **kwargs):
        super(CryptonTrade, self).__init__(*args, **kwargs)

    def start(self, market_symbol):
        while True:
            success, best_exchange_asks, best_exchange_bids = self.fetch_orders(market_symbol)

            if success is False:
                self.sleep()
                continue

            if self.check_arbitrage(best_exchange_asks, best_exchange_bids) is False:
                self.sleep()
                continue

            self.initiate_order()

            # For now we break
            break

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

    @staticmethod
    def calculate_order_quantity(best_ask, best_bid):
        base_currency = best_ask.exchange_market.base_coin
        ask_offer_quantity = best_ask.ask_quantity
        ask_exchange_quantity = best_ask.exchange.balance.get(base_currency, {}).get('available', 0.0)

        quote_currency = best_bid.exchange_market.base_coin
        bid_offer_quantity = best_bid.bid_quantity
        bid_exchange_quantity = best_bid.exchange.balance.get(quote_currency, {}).get('available', 0.0)

        return min(ask_offer_quantity, ask_exchange_quantity, bid_offer_quantity, bid_exchange_quantity)

    def verify_profit_margin(self, best_ask, best_bid):
        # Profit in percentage
        margin = best_bid.price_with_fee - best_ask.price_with_fee
        profit_perc = margin / best_bid.price_with_fee

        if profit_perc >= self.DEFAULT_MIN_PROFIT_MARGIN:
            return True

        # Profit in amount
        profit_amount = best_bid.cost_with_fee - best_ask.cost_with_fee
        if profit_amount >= self.DEFAULT_MIN_PROFIT_AMOUNT:
            return True

        return False

    def check_arbitrage(self, best_exchange_asks, best_exchange_bids):
        best_ask = min(best_exchange_asks)
        best_bid = max(best_exchange_bids)

        if best_ask.exchange_id == best_bid.exchange_id:
            self.notify("Skipping: Best ask and best bid are on the same exchange")
            return False

        if best_ask.price >= best_bid.price:
            self.notify("Skipping: There is no arbitrage")
            return False

        if self.verify_profit_margin(best_ask, best_bid):
            self.notify("Skipping: Not enough profit")
            return False

        quantity = self.calculate_order_quantity(best_ask, best_bid)
        if quantity <= 0.0:
            msg = "Skipping: No quantity left for sale"
            self.notify(msg.format(profit_margin, self.minimal_profit_margin))
            return False

        print(
            "Lowest ask (with fee): {} ({})".format(
                best_ask.bid_price, best_ask.bid_price_with_fee
            )
        )
        print(
            "Highest bid (with fee): {} ({})".format(
                best_bid.bid_price, best_bid.bid_price_with_fee
            )
        )
        print("Profit margin {}".format(profit_margin))

        # TODO: Check if we can get more bids to find the highest. Pagination?
        # TODO:

        return True

    def initiate_order(self):
        # WIP
        print("Ordering")


bot = CryptonTrade(EXCHANGE_CONFIGS, verbose=True)
bot.start("BTC/USDT")
