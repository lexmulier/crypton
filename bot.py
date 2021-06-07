from time import sleep
import asyncio

from exchanges import Exchange


class Crypton(object):

    _sleep_seconds = 1
    market = None

    def __init__(self, exchange_configs, verbose=False):
        self.exchange_configs = exchange_configs
        self.verbose = verbose

        self.exchanges = None
        self.initiate_exchanges()

    def initiate_exchanges(self):
        exchanges = {}
        for exchange_id, exchange_config in self.exchange_configs.items():
            exchange = Exchange(
                exchange_id,
                exchange_config,
                preload_market=self.market,
                verbose=self.verbose
            )

            exchanges[exchange_id] = exchange

        self.exchanges = exchanges
        self._fetch_exchange_info()

    def _fetch_exchange_info(self):
        loop = asyncio.get_event_loop()
        tasks = [exchange.prepare() for exchange in self.exchanges.values()]
        loop.run_until_complete(asyncio.gather(*tasks))

    def sleep(self, seconds=None):
        seconds = seconds if seconds is not None else self._sleep_seconds
        sleep(seconds)

    def notify(self, *args):
        if self.verbose:
            print(*args)


