from utils import sleep_now


class Collector:
    _type_request = "request"
    _type_stream = "stream"

    def __init__(self, market, exchange_market, settings=None):
        self.market = market
        self.exchange_market = exchange_market

        self.collect_type = settings.get("collector_type", self._type_request)
        self.sleep_time = settings.get("sleep_time", 0.1)

        self.changed = False

        self.ask = None
        self.bid = None

        self.set_first_order_books()

    def set_first_order_books(self):
        success, ask, bid = self.exchange_market.get_orders_sync()
        if not success:
            raise ValueError("Something went wrong retrieving orderbook")

        self.ask = ask
        self.bid = bid

    def start(self):
        getattr(self, self.collect_type)()

    def stream(self):
        pass

    def request(self):
        while True:
            if self.sleep_time:
                sleep_now(seconds=self.sleep_time)

            success, ask, bid = self.exchange_market.get_orders_sync()
            if not success:
                continue

            if self.ask.first_price != ask.first_price or self.bid.first_price != bid.first_price:
                self.ask = ask
                self.bid = bid
                self.changed = True


def create_collector_instances(exchanges, settings):
    market = settings["market"]

    left_exchange, right_exchange = exchanges.values()

    left_collector = Collector(
        market,
        left_exchange.markets[market],
        settings["settings"][left_exchange.exchange_id]
    )
    right_collector = Collector(
        market,
        right_exchange.markets[market],
        settings["settings"][right_exchange.exchange_id]
    )

    return left_collector, right_collector
