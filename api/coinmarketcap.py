import requests

from config import COIN_MARKET_CAP_API_KEY


class CoinMarketCapAPI(object):
    _base_url = "https://pro-api.coinmarketcap.com"
    _headers = {
        "X-CMC_PRO_API_KEY": COIN_MARKET_CAP_API_KEY,
        "Content-Type": "application/json"
    }

    def fetch_coin_info(self):
        url = f"{self._base_url}/v1/cryptocurrency/map"
        response = requests.get(url, headers=self._headers)
        response_data = response.json()

        if response.status_code != 200 and response_data["status"]["error_code"] != 0:
            return

        coins = {}
        for coin in response_data["data"]:
            symbol = coin["symbol"]

            coins[symbol] = {
                "symbol": symbol,
                "name": coin["name"],
                "rank": coin["rank"],
                "active": coin["is_active"],
            }

        return coins
