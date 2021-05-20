from bot import Crypton
from config import KRAKEN_CONFIG, KUCOIN_CONFIG, LATOKEN_CONFIG

EXCHANGE_CONFIGS = {
    "kraken": KRAKEN_CONFIG,
    "latoken": LATOKEN_CONFIG,
    "kucoin": KUCOIN_CONFIG
}

bot = Crypton(EXCHANGE_CONFIGS)
bot.start("BTC/USDT")
