import base64
import datetime
import hashlib
import hmac

from api.base import BaseAPI


class KuCoinAPI(BaseAPI):
    _base_url = "https://api.kucoin.com"

    def __init__(self, *args, **kwargs):
        super(KuCoinAPI, self).__init__(*args, **kwargs)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode()
        self._trading_password = self.config["trading_password"].encode()
        self._password = self.config["password"].encode()

    async def fetch_markets(self):
        url = self._base_url + "/api/v1/symbols"
        response = await self.get(url)
        return [
            {
                "symbol": "{}/{}".format(x["baseCurrency"], x["quoteCurrency"]),
                "base": x["baseCurrency"],
                "quote": x["quoteCurrency"]
            }
            for x in response["data"]
        ]

    async def fetch_order_book(self, symbol, limit=None):
        url = self._base_url + "/api/v1/market/orderbook/level2_{}?symbol={}".format(
            limit or 20, symbol.replace("/", "-")
        )
        response = await self.get(url)
        asks = [[float(x[0]), float(x[1])] for x in response["data"]["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["data"]["bids"]]
        return asks, bids

    async def fetch_fees(self, symbol):
        endpoint = "/api/v1/trade-fees?symbols={}".format(symbol.replace("/", "-"))
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {
            "taker": float(response["data"][0]["takerFeeRate"]),
            "maker": float(response["data"][0]["makerFeeRate"])
        }

    async def fetch_balance(self):
        endpoint = "/api/v1/accounts"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {row["currency"]: float(row["available"]) for row in response["data"]}

    async def create_order(self, _id, symbol, qty, price, side, _type=None):
        endpoint = "/api/v1/orders"
        url = self._base_url + endpoint
        data = {
            "clientOid": str(_id),
            "side": side,
            "symbol": symbol.replace("/", "-"),
            "type": "limit",
            "size": str(qty),
            "price": str(price),
            "timeInForce": "IOC",
            "hidden": False,
            "iceberg": False,
        }

        compact_data = self._compact_json_dict(data)
        headers = self._get_headers(endpoint, method="POST", compact_data=compact_data)

        response = await self.post(url, data=compact_data, headers=headers)

        if response.get('code') != '200000':
            self.notify("Error on {} order: {}".format(side, response.get("msg", "Error message N/A")))
            return False, response

        self.notify("Exchange order ID", _id)

        return True, _id

    async def cancel_order(self, order_id, *args, **kwargs):
        endpoint = "/api/v1/order/client-order/{}".format(str(order_id))
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint, method="DELETE")
        response = await self.delete(url, headers=headers)

        if response.get('code') != '200000':
            self.notify("Error on cancel order: {}".format(response.get("msg", "Error message N/A")))
            return False

        return True

    async def fetch_order_status(self, order_id):
        endpoint = "/api/v1/order/client-order/{}".format(str(order_id))
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)

        data = {
            "price": float(response["data"]["price"]),
            "quantity": float(response["data"]["size"]),
            "fee": float(response["data"]["fee"]),
            "timestamp": datetime.datetime.fromtimestamp(response["data"]["createdAt"] / 1000.0),
            "filled": not response["data"]["isActive"] and not response["data"]["cancelExist"]
        }

        return data

    @property
    def _encoded_passphrase(self):
        return base64.b64encode(
            hmac.new(self._secret, self._password, hashlib.sha256).digest()
        ).decode()

    @staticmethod
    def _get_params_for_sig(data):
        return '&'.join(["{}={}".format(key, data[key]) for key in data])

    def _generate_signature(self, nonce, method, endpoint, data=None, compact_data=None):
        data_json = ""
        if method == "GET" and data:
            query_string = self._get_params_for_sig(data)
            endpoint = "{}?{}".format(endpoint, query_string)
        elif method == "POST" and compact_data:
            data_json = compact_data
        elif method == "POST" and data:
            data_json = self._compact_json_dict(data)
        sig_str = ("{}{}{}{}".format(nonce, method.upper(), endpoint, data_json)).encode('utf-8')
        m = hmac.new(self._secret, sig_str, hashlib.sha256)
        return base64.b64encode(m.digest()).decode()

    def _get_headers(self, endpoint, method="GET", data=None, compact_data=None):
        nonce = self._nonce()
        return {
            "KC-API-SIGN": self._generate_signature(nonce, method, endpoint, data=data, compact_data=compact_data),
            "KC-API-TIMESTAMP": nonce,
            "KC-API-KEY": self._api_key,
            "KC-API-PASSPHRASE": self._encoded_passphrase,
            "KC-API-KEY-VERSION": "2"
        }
