import base64
import hashlib
import hmac

import time

from api.base import APIBase


class AscendexAPI(APIBase):

    _big_coins = [
        'BTC', 'ETH', 'XRP', 'USDT', 'BCH', 'LTC', 'EOS', 'BNB', 'BSV',
        'TRX', 'LINK', 'HT', 'OKB', 'ATOM', 'DASH', 'ETC', 'NEO', 'XEM',
        'FIL', 'UNI', 'FTT', 'ADA', 'ALGO', 'ZEC', 'DOT', 'XLM', 'DOGE'
    ]
    _base_url = "https://ascendex.com"
    _private_base_url = "https://ascendex.com/6"

    def __init__(self, exchange):
        super(AscendexAPI, self).__init__(exchange)
        self._api_key = self.config["apiKey"]
        self._secret = base64.b64decode(self.config["secret"])
        self._uuid = None

    async def fetch_markets(self):
        url = self._base_url + "/api/pro/v1/products"
        response = await self.get(url)
        markets = [
            {
                "symbol": "{}/{}".format(x["baseAsset"], x["quoteAsset"]),
                "base": x["baseAsset"],
                "quote": x["quoteAsset"]
            }
            for x in response["data"]
        ]
        return markets

    async def fetch_balance(self):
        url = self._private_base_url + "/api/pro/v1/cash/balance"
        headers = self._get_headers("balance", self._nonce())
        response = await self.get(url, headers=headers)
        return {row["asset"]: float(row["availableBalance"]) for row in response["data"]}

    async def fetch_order_book(self, symbol, **kwargs):
        url = "https://ascendex.com/api/pro/v1/depth?symbol={}".format(symbol)
        response = await self.get(url)
        asks = [[float(x[0]), float(x[1])] for x in response["data"]["data"]["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["data"]["data"]["bids"]]
        return asks, bids

    async def fetch_fees(self, symbol):
        if symbol.split('/')[0] in self._big_coins:
            fee = 0.1
        else:
            fee = 0.2
        return {"maker": fee, "taker": fee}

    async def fetch_exchange_specifics(self):
        await self._fetch_uuid()

    async def _fetch_uuid(self):
        headers = self._get_headers("info", self._nonce())
        url = self._base_url + "/api/pro/v1/info"
        response = await self.get(url, headers=headers)
        self._uuid = response["data"]["userUID"]

    async def create_order(self, _id, symbol, qty, price, side, _type=None, params=None):
        url = self._private_base_url + "/api/pro/v1/cash/order"
        nonce = self._nonce()
        exchange_order_id = self._create_order_id(_id, nonce)
        data = {
            "id": exchange_order_id,
            "time": nonce,
            "symbol": symbol,
            "orderPrice": str(price),
            "orderQty": str(qty),
            "orderType": "limit",
            "side": side,
            "timeInForce": "IOC"
        }
        print(data)
        headers = self._get_headers("order", nonce)
        print(headers)
        response = await self.post(url, data, headers=headers)

        print(response)

        return exchange_order_id

    def _create_order_id(self, _id, nonce, source="a"):
        return (source + format(int(nonce), 'x')[-11:] + self._uuid[-11:] + str(_id)[-9:])[:32]

    @staticmethod
    def _generate_signature(nonce, endpoint, secret):
        sig_str = "{}+{}".format(nonce, endpoint)
        sig_str = bytearray(sig_str.encode("utf-8"))
        signature = hmac.new(secret, sig_str, hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode("utf-8")
        return signature_b64

    def _get_headers(self, endpoint, nonce):
        return {
            "x-auth-key": self._api_key,
            "x-auth-signature": self._generate_signature(nonce, endpoint, self._secret),
            "x-auth-timestamp": nonce,
        }
