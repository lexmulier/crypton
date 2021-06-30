import base64
import hashlib
import hmac
import datetime

from api.base import BaseAPI
from utils import exception_logger


class AscendexAPI(BaseAPI):

    _big_coins = [
        'BTC', 'ETH', 'XRP', 'USDT', 'BCH', 'LTC', 'EOS', 'BNB', 'BSV',
        'TRX', 'LINK', 'HT', 'OKB', 'ATOM', 'DASH', 'ETC', 'NEO', 'XEM',
        'FIL', 'UNI', 'FTT', 'ADA', 'ALGO', 'ZEC', 'DOT', 'XLM', 'DOGE'
    ]
    _base_url = "https://ascendex.com"
    _private_base_url = "https://ascendex.com/6"

    def __init__(self, *args, **kwargs):
        super(AscendexAPI, self).__init__(*args, **kwargs)
        self._api_key = self.config["apiKey"]
        self._secret = base64.b64decode(self.config["secret"])
        self._uuid = None

    @exception_logger()
    async def fetch_markets(self):
        url = self._base_url + "/api/pro/v1/products"
        response = await self.get(url)
        markets = [
            {
                "symbol": f"{x['baseAsset']}/{x['quoteAsset']}",
                "base": x["baseAsset"],
                "quote": x["quoteAsset"],
                "min_quote_qty": float(x["minNotional"]),
                "base_precision": self._precision(x["lotSize"]),
                "price_precision": self._precision(x["tickSize"])
            }
            for x in response["data"]
        ]
        return markets

    @exception_logger()
    async def fetch_balance(self):
        url = self._private_base_url + "/api/pro/v1/cash/balance"
        headers = self._get_headers("balance", self._nonce())
        response = await self.get(url, headers=headers)
        return {row["asset"]: float(row["availableBalance"]) for row in response["data"]}

    @exception_logger()
    async def fetch_order_book(self, symbol, **kwargs):
        url = f"https://ascendex.com/api/pro/v1/depth?symbol={symbol}"
        response = await self.get(url)
        asks = [[float(x[0]), float(x[1])] for x in response["data"]["data"]["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["data"]["data"]["bids"]]
        return asks, bids

    @exception_logger()
    async def fetch_fees(self, symbol):
        if symbol.split('/')[0] in self._big_coins:
            fee = 0.001
        else:
            fee = 0.002
        return {"maker": fee, "taker": fee}

    async def fetch_exchange_specifics(self):
        await self._fetch_uuid()

    @exception_logger()
    async def _fetch_uuid(self):
        headers = self._get_headers("info", self._nonce())
        url = self._base_url + "/api/pro/v1/info"
        response = await self.get(url, headers=headers)
        self._uuid = response["data"]["userUID"]

    @exception_logger()
    async def fetch_order_status(self, order_id, **kwargs):
        headers = self._get_headers("order/status", self._nonce())
        url = f"{self._private_base_url}/api/pro/v1/cash/order/status?orderId={str(order_id)}"
        response = await self.get(url, headers=headers)

        if response.get('code', 0) != 0:
            self.log.info(f"Error status retrieve: {response}")
            return

        data = {
            "price": float(response["data"]["price"]),
            "base_quantity": float(response["data"]["orderQty"]),
            "fee": float(response["data"]["cumFee"]),
            "timestamp": datetime.datetime.fromtimestamp(response["data"]["lastExecTime"] / 1000.0),
            "filled": response["data"]["status"] == "Filled"
        }

        return data

    @exception_logger()
    async def fetch_order_history(self):
        headers = self._get_headers("order/hist/current", self._nonce())
        url = self._private_base_url + "/api/pro/v1/cash/order/hist/current"
        response = await self.get(url, headers=headers)
        print(response)

    @exception_logger()
    async def create_order(self, _id, symbol, qty, price, side):
        url = self._private_base_url + "/api/pro/v1/cash/order"
        nonce = self._nonce()
        order_id = self._create_order_id(_id, nonce)

        data = {
            "id": order_id,
            "time": nonce,
            "symbol": symbol,
            "orderPrice": str(price),
            "orderQty": str(qty),
            "orderType": "limit",
            "side": side,
            "timeInForce": "IOC"
        }

        compact_data = self._compact_json_dict(data)
        headers = self._get_headers("order", nonce)

        response = await self.post(url, compact_data, headers=headers)

        if response.get('code', 0) != 0:
            self.log.info(f"Error on {side} order: {response}")
            return False, response

        exchange_order_id = response["data"]["info"]["orderId"]
        self.log.info(f"Exchange order ID {exchange_order_id}")

        return True, exchange_order_id

    @exception_logger()
    async def cancel_order(self, order_id, symbol=None, *args, **kwargs):
        url = self._private_base_url + "/api/pro/v1/cash/order"
        nonce = self._nonce()
        data = {
            "orderId": order_id,
            "symbol": symbol,
            "time": nonce
        }
        compact_data = self._compact_json_dict(data)
        headers = self._get_headers("order", nonce)
        response = await self.delete(url, data=compact_data, headers=headers)

        if response.get('code', 0) != 0:
            self.log.info(f"Error on cancel order: {response}")
            return response

        return response['data']['status'] == 'Ack'

    def _create_order_id(self, _id, nonce, source="a"):
        return (source + format(int(nonce), 'x')[-11:] + self._uuid[-11:] + str(_id)[-9:])[:32]

    @staticmethod
    def _generate_signature(nonce, endpoint, secret):
        sig_str = f"{nonce}+{endpoint}"
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
