from api.ascendex import AscendexAPI
from api.ccxt import CcxtAPI
from api.dextrade import DexTradeAPI
from api.indoex import IndoExAPI
from api.kucoin import KuCoinAPI

API_CLASS_MAPPING = {
    "ascendex": AscendexAPI,
    "binance": CcxtAPI,
    "liquid": CcxtAPI,
    "timex": CcxtAPI,
    "latoken": CcxtAPI,
    "kucoin": KuCoinAPI,
    "kraken": CcxtAPI,
    "binance": CcxtAPI,
    "dextrade": DexTradeAPI,
    "indoex": IndoExAPI,
}


def get_client(exchange):
    if exchange.exchange_id not in API_CLASS_MAPPING:
        raise ValueError("API wrapper config for {} does not exist".format(exchange.exchange_id))

    wrapper = API_CLASS_MAPPING[exchange.exchange_id](exchange.api_config, exchange=exchange)
    return wrapper
