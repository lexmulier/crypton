from time import sleep

from exchanges import Exchange


class Crypton(object):

    _sleep_seconds = 1

    def __init__(self, exchange_configs, verbose=False):
        self.exchange_configs = exchange_configs
        self.verbose = verbose

        self.exchanges = self.initiate_exchanges()

    def initiate_exchanges(self):
        return {
            exchange_id: Exchange(exchange_id, exchange_config, verbose=self.verbose)
            for exchange_id, exchange_config in self.exchange_configs.items()
        }

    def sleep(self, seconds=None):
        seconds = seconds if seconds is not None else self._sleep_seconds
        sleep(seconds)

    def notify(self, *args):
        if self.verbose:
            print(*args)


