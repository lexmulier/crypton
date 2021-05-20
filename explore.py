from bot import CryptonBase
from config import KRAKEN_CONFIG, KUCOIN_CONFIG, LATOKEN_CONFIG

EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    "latoken": LATOKEN_CONFIG,
    "kucoin": KUCOIN_CONFIG
}


class Explore(CryptonBase):

    def __init__(self, *args, **kwargs):
        super(Explore, self).__init__(*args, **kwargs)

    



if __name__ == "__main__":
    bot = Explore(EXCHANGE_CONFIGS)

