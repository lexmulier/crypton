from api.ascendex import AscendexAPI
from api.ccxt import CcxtAPI
from api.dextrade import DexTradeAPI
from api.indoex import IndoExAPI
from api.kucoin import KuCoinAPI
from api.latoken import LATokenAPI
from api.binance import BinanceAPI

API_CLASS_MAPPING = {
    "ascendex": AscendexAPI,
    "binance": BinanceAPI,
    "latoken": LATokenAPI,
    "kucoin": KuCoinAPI,
    "dextrade": DexTradeAPI,
    "indoex": IndoExAPI,
}


def get_client(exchange):
    api_class = API_CLASS_MAPPING.get(exchange.exchange_id, CcxtAPI)
    wrapper = api_class(exchange.api_config, exchange=exchange)
    return wrapper
