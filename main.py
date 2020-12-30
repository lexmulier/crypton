import ccxt

from utils import handle_bad_requests
from config import KRAKEN_CONFIG, KUCOIN_CONFIG


EXCHANGE_CONFIGS = {"kraken": KRAKEN_CONFIG, "kucoin": KUCOIN_CONFIG}


class Exchange(object):
    def __init__(self, exchange_id, api_config):
        self.exchange_id = exchange_id
        self.api_config = api_config

        self.client = self.initiate_exchange_class()
        self.market_info = self.load_markets()
        self.market_symbols = self.load_market_symbols()

    def initiate_exchange_class(self):
        exchange_class = getattr(ccxt, self.exchange_id)
        exchange_api = exchange_class(self.api_config)
        return exchange_api

    @handle_bad_requests()
    def load_markets(self):
        return self.client.load_markets()

    def load_market_symbols(self):
        return list(self.market_info.keys())

    def get_market_info(self, market_symbol):
        market_info = self.market_info.get(market_symbol)
        if market_info is None:
            raise ValueError(
                "Market {} not found in this exchange {}".format(
                    market_symbol, self.exchange_id
                )
            )
        return market_info

    @handle_bad_requests()
    def get_balance(self):
        response = self.client.fetch_balance()
        if response["info"]["data"]:
            return response["info"]["data"]
        return {}

    @handle_bad_requests(max_retries=1)
    def get_order_book(self, market_symbol):
        open_orders = self.client.fetch_order_book(symbol=market_symbol)
        return open_orders["asks"], open_orders["bids"]

    def get_order(self, market_symbol):
        try:
            asks, bids = self.get_order_book(market_symbol)
        except Exception:
            return False, None
        return True, OrderBook(self, market_symbol, asks, bids)


class OrderBook(object):
    def __init__(self, exchange, market_symbol, asks, bids):
        self.exchange = exchange
        self.market_symbol = market_symbol
        self.asks = asks
        self.bids = bids

        self.order_asks_and_bids()

    def order_asks_and_bids(self):
        # TODO: Check if necessary, ordering takes time
        self.asks = sorted(self.asks, key=lambda ask: ask[0])
        self.bids = sorted(self.bids, key=lambda bid: bid[0], reverse=True)

    @property
    def ask_price(self):
        return self.asks[0][0]

    @property
    def ask_qty(self):
        return self.asks[0][1]

    @property
    def ask_id(self):
        if len(self.asks[0]) == 3:
            return self.asks[0][2]
        return None

    @property
    def bid_price(self):
        return self.bids[0][0]

    @property
    def bid_qty(self):
        return self.bids[0][1]

    @property
    def bid_id(self):
        if len(self.bids[0]) == 3:
            return self.bids[0][2]
        return None

    def __lt__(self, other_exchange):
        return self.ask_price < other_exchange.ask_price

    def __le__(self, other_exchange):
        return self.ask_price <= other_exchange.ask_price

    def __eq__(self, other_exchange):
        return self.ask_price == other_exchange.ask_price and self.bid_price == other_exchange.bid_price

    def __ne__(self, other_exchange):
        return self.ask_price != other_exchange.ask_price and self.bid_price != other_exchange.bid_price

    def __gt__(self, other_exchange):
        return self.bid_price > other_exchange.bid_price

    def __ge__(self, other_exchange):
        return self.bid_price >= other_exchange.bid_price

    def __str__(self):
        return str({
            'exchange_id': self.exchange.exchange_id,
            'market_symbol': self.market_symbol,
            'ask_price': self.ask_price,
            'ask_qty': self.ask_qty,
            'ask_id': self.ask_id,
            'bid_price': self.bid_price,
            'bid_qty': self.bid_qty,
            'bid_id': self.bid_id,
        })


class Crypton(object):
    def __init__(self, market_symbol, exchange_configs):
        self.market_symbol = market_symbol
        self.exchange_configs = exchange_configs

    @property
    def exchanges(self):
        return {
            exchange_id: Exchange(exchange_id, exchange_config)
            for exchange_id, exchange_config in self.exchange_configs.items()
        }

    def get_orders(self):
        order_books = []
        for exchange in self.exchanges.values():
            print("Checking", exchange.exchange_id)

            success, order = exchange.get_order(self.market_symbol)
            if success is False:
                print(exchange.exchange_id, "API Failed. We need to retry all Exchanges")
                return False, []

            order_books.append(order)

        return True, order_books

    def start(self):
        while True:
            success, order_books = self.get_orders()
            if success is False:
                continue

            lowest_ask_order = min(order_books)
            highest_bid_order = max(order_books)

            if self.verify_profitability(lowest_ask_order, highest_bid_order) is False:
                print("Order is not profitable")
                continue

            self.initiate_order()

    def verify_profitability(self, lowest_ask_order, highest_bid_order):
        print(lowest_ask_order.ask_price, highest_bid_order.bid_price)
        return True

    def initiate_order(self):
        print('Ordering')


crypton = Crypton("BTC/USDT", EXCHANGE_CONFIGS)
