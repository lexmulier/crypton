import asyncio
import threading

from log import Notify
from exchanges import initiate_exchanges
from trader.trade import CryptonTrade
from trader.collector import create_collector_instances
from trader.utils import refresh_exchange_balances, update_local_balances_from_exchanges, upsert_market_pair
from utils import sleep_now


class CryptonLooper:
    MINIMAL_SLEEP_SECONDS = 0.01
    POST_TRADE_SLEEP_SECONDS = 2.0

    def __init__(self, settings, notifier=None):
        self.settings = settings

        if notifier is None:
            self.notifier = Notify(level="info").initiate()
        else:
            self.notifier = notifier

        self.market = self.settings["market"]
        self.exchange_ids = self.settings["exchanges"]

        self.market_pair_id = upsert_market_pair(self.market, self.exchange_ids)

        self.exchanges = initiate_exchanges(
            self.exchange_ids,
            preload_market=self.market,
            exchange_settings=settings["settings"],
            notifier=self.notifier
        )
        self.left, self.right = create_collector_instances(self.exchanges, settings)

    def start(self):
        for thread_target in [self.left.start, self.right.start, self.loop]:
            threading.Thread(target=thread_target).start()

    def loop(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

        counter = 0
        while True:
            sleep_now(seconds=self.MINIMAL_SLEEP_SECONDS)

            # Refresh balance from the database and sometimes from the exchange
            refresh_exchange_balances(counter, self.exchanges)

            if self.left.changed or self.right.changed:
                self.left.changed = False
                self.right.changed = False

                trader = CryptonTrade(
                    self.market,
                    self.exchanges,
                    market_pair_id=self.market_pair_id,
                    performance_mode=self.settings.get("performance_mode", False),
                    notifier=self.notifier,
                )
                trader.start([self.left.ask, self.right.ask], [self.left.bid, self.right.bid])

                # Update the balance information with the latest from the exchange
                if trader.successful is not None:
                    sleep_now(seconds=self.POST_TRADE_SLEEP_SECONDS)
                    update_local_balances_from_exchanges(self.exchanges)

            counter += 1
