from ..trade import CryptonTrade


EXCHANGE_CONFIGS = {
    "exchange_1": {
        "apiKey": "api_key1",
        "secret": "secret_key1",
    },
    "exchange_2": {
        "apiKey": "api_key2",
        "secret": "secret_key2",
    }
}


def test_check_arbitrage():
    bot = CryptonTrade(EXCHANGE_CONFIGS, verbose=True)

