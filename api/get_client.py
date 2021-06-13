from api.ccxt import CcxtAPI
from api.dextrade import DexTradeAPI
from api.indoex import IndoExAPI


def get_client(exchange, session):
    _api_class_mapping = {
        "ascendex": CcxtAPI,
        "binance": CcxtAPI,
        "liquid": CcxtAPI,
        "timex": CcxtAPI,
        "latoken": CcxtAPI,
        "kucoin": CcxtAPI,
        "kraken": CcxtAPI,
        "binance": CcxtAPI,
        "dextrade": DexTradeAPI,
        "indoex": IndoExAPI,
    }

    if exchange.exchange_id not in _api_class_mapping:
        raise ValueError("API wrapper config for {} does not exist".format(exchange.exchange_id))

    wrapper = _api_class_mapping[exchange.exchange_id](exchange, session)
    #exchange.notify("Using API {} for {}".format(wrapper.__class__.__name__, exchange.exchange_id))
    return wrapper