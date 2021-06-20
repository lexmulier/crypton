import asyncio

from exchanges import Exchange


class CryptonBase(object):

    sleep_seconds = 0.1

    market = None
    sleep = False

    def __init__(self, exchange_names, verbose=False):
        self.verbose = verbose
        self.exchanges = None

        self.initiate_exchanges()






