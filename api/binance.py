import hashlib
import hmac

from api.base import BaseAPI


class BinanceAPI(BaseAPI):
    _base_url = "https://api.binance.com"

    def __init__(self, *args, **kwargs):
        super(BinanceAPI, self).__init__(*args, **kwargs)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode('utf-8')

    @property
    def _headers(self):
        return {
            'Content-Type': 'application/json;charset=utf-8',
            'X-MBX-APIKEY': self._api_key
        }

    async def fetch_markets(self):
        url = self._base_url + "/api/v3/exchangeInfo"
        response = await self.get(url)
        return [
            {
                "symbol": "{}/{}".format(x["baseAsset"], x["quoteAsset"]),
                "base": x["baseAsset"],
                "quote": x["quoteAsset"],
                "min_base_qty": 0.0,
                "min_quote_qty": 0.0,
                "base_precision": int(x["baseAssetPrecision"]),
                "quote_precision": int(x["quoteAssetPrecision"]),
                "price_precision": int(x["quotePrecision"]),
            }
            for x in response["symbols"]
        ]

    async def fetch_balance(self):
        endpoint = "/api/v3/account"
        url = self._get_request_url(endpoint)
        response = await self.get(url, headers=self._headers)
        return {
            row["asset"]: float(row["free"])
            for row in response["balances"]
        }

    async def fetch_fees(self, symbol):
        endpoint = "/sapi/v1/asset/tradeFee"
        data = {"symbol": symbol.replace("/", "")}
        url = self._get_request_url(endpoint, data=data)
        response = await self.get(url, headers=self._headers)
        return {
            "taker": float(response[0]["takerCommission"]),
            "maker": float(response[0]["makerCommission"])
        }

    async def fetch_order_book(self, symbol, **kwargs):
        endpoint = "/api/v3/depth"
        data = {"symbol": symbol.replace("/", "")}
        url = self._get_request_url(endpoint, data=data)
        response = await self.get(url, headers=self._headers)

        asks = [[float(x[0]), float(x[1])] for x in response["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["bids"]]
        return asks, bids

    async def create_order(self, _id, symbol, qty, price, side):
        endpoint = "/api/v3/order"

        data = {
            "symbol": symbol.replace("/", ""),
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "IOC",
            "quantity": qty,
            "newClientOrderId": str(_id),
            "price": str(price),
            "timestamp": self._nonce()
        }

        url = self._get_request_url(endpoint, data=data)
        compact_data = self._compact_json_dict(data)
        response = await self.post(url, data=compact_data, headers=self._headers)

        print(response)

        # if response.get("code") != "200000":
        #     self.notify("Error on {} order: {}".format(side, response.get("msg", "Error message N/A")))
        #     return False, response

        self.notify("Exchange order ID", _id)

        return True, _id
    #
    # async def cancel_order(self, order_id, *args, **kwargs):
    #     endpoint = "/api/v1/order/client-order/{}".format(str(order_id))
    #     url = self._base_url + endpoint
    #     headers = self._get_headers(endpoint, method="DELETE")
    #     response = await self.delete(url, headers=headers)
    #
    #     if response.get("code") != "200000":
    #         self.notify("Error on cancel order: {}".format(response.get("msg", "Error message N/A")))
    #         return False
    #
    #     return True
    #
    # async def fetch_order_status(self, order_id):
    #     endpoint = "/api/v1/order/client-order/{}".format(str(order_id))
    #     url = self._base_url + endpoint
    #     headers = self._get_headers(endpoint)
    #     response = await self.get(url, headers=headers)
    #
    #     data = {
    #         "price": float(response["data"]["price"]),
    #         "base_quantity": float(response["data"]["size"]),
    #         "fee": float(response["data"]["fee"]),
    #         "timestamp": datetime.datetime.fromtimestamp(response["data"]["createdAt"] / 1000.0),
    #         "filled": not response["data"]["isActive"] and not response["data"]["cancelExist"]
    #     }
    #
    #     return data
    #

    def _get_request_url(self, endpoint, data=None):
        if data is None:
            query_string = 'timestamp={}'.format(self._nonce())
        else:
            query_string = self._get_params_for_sig(data)

        sig = hmac.new(self._secret, query_string.encode('utf-8'), hashlib.sha256).hexdigest()

        return "{}{}?{}&signature={}".format(self._base_url, endpoint, query_string, sig)
