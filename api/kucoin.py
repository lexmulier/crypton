import base64
import datetime
import hashlib
import hmac

from api.base import BaseAPI
from utils import exception_logger


class KuCoinAPI(BaseAPI):
    _base_url = "https://api.kucoin.com"

    def __init__(self, *args, **kwargs):
        super(KuCoinAPI, self).__init__(*args, **kwargs)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode()
        self._trading_password = self.config["trading_password"].encode()
        self._password = self.config["password"].encode()

    @exception_logger()
    async def fetch_markets(self):
        url = self._base_url + "/api/v1/symbols"
        response = await self.get(url)
        return [
            {
                "symbol": f"{x['baseCurrency']}/{x['quoteCurrency']}",
                "base": x["baseCurrency"],
                "quote": x["quoteCurrency"],
                "min_base_qty": float(x["baseMinSize"]),
                "min_quote_qty": float(x["quoteMinSize"]),
                "base_precision": self._precision(x["baseIncrement"]),
                "quote_precision": self._precision(x["baseIncrement"]),
                "price_precision": self._precision(x["priceIncrement"])
            }
            for x in response["data"]
        ]

    @exception_logger()
    async def fetch_order_book(self, symbol, limit=None):
        url = f"{self._base_url}/api/v1/market/orderbook/level2_{limit or 20}?symbol={symbol.replace('/', '-')}"
        response = await self.get(url)
        asks = [[float(x[0]), float(x[1])] for x in response["data"]["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["data"]["bids"]]
        return asks, bids

    @exception_logger()
    async def fetch_fees(self, symbol):
        endpoint = f"/api/v1/trade-fees?symbols={symbol.replace('/', '-')}"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {
            "taker": float(response["data"][0]["takerFeeRate"]),
            "maker": float(response["data"][0]["makerFeeRate"])
        }

    @exception_logger()
    async def fetch_balance(self):
        endpoint = "/api/v1/accounts"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {
            row["currency"]: float(row["available"])
            for row in response["data"]
            if row["type"] == "trade"
        }

    @exception_logger()
    async def create_order(self, _id, symbol, qty, price, side):
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
            self.log.info(f"Error on {side} order: {response}")
            return False, response

        self.log.info(f"Exchange order ID {_id}")

        return True, _id

    @exception_logger()
    async def cancel_order(self, order_id, *args, **kwargs):
        endpoint = f"/api/v1/order/client-order/{str(order_id)}"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint, method="DELETE")
        response = await self.delete(url, headers=headers)

        if response.get('code') != '200000':
            self.log.info(f"Error on cancel order: {response}")
            return False

        return True

    @exception_logger()
    async def fetch_order_status(self, order_id, **kwargs):
        endpoint = f"/api/v1/order/client-order/{str(order_id)}"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)

        data = {
            "price": float(response["data"]["price"]),
            "base_quantity": float(response["data"]["size"]),
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

    def _generate_signature(self, nonce, method, endpoint, data=None, compact_data=None):
        data_json = ""
        if method == "GET" and data:
            query_string = self._get_params_for_sig(data)
            endpoint = f"{endpoint}?{query_string}"
        elif method == "POST" and compact_data:
            data_json = compact_data
        elif method == "POST" and data:
            data_json = self._compact_json_dict(data)
        sig_str = f"{nonce}{method.upper()}{endpoint}{data_json}".encode('utf-8')
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
