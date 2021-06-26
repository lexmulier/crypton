import datetime
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

        markets = []
        for market in response["symbols"]:
            min_base_qty = 0.0
            min_quote_qty = 0.0
            for filter_row in market["filters"]:
                if filter_row["filterType"] == "LOT_SIZE":
                    min_base_qty = float(filter_row["minQty"])
                if filter_row["filterType"] == "MIN_NOTIONAL":
                    min_quote_qty = float(filter_row["minNotional"])

            markets.append({
                "symbol": "{}/{}".format(market["baseAsset"], market["quoteAsset"]),
                "base": market["baseAsset"],
                "quote": market["quoteAsset"],
                "min_base_qty": min_base_qty,
                "min_quote_qty": min_quote_qty,
                "base_precision": int(market["baseAssetPrecision"]),
                "quote_precision": int(market["quoteAssetPrecision"]),
                "price_precision": int(market["quotePrecision"]),
            })

        return markets

    async def fetch_balance(self):
        endpoint = "/api/v3/account"
        url = self._get_request_url(endpoint, timestamp=self._nonce())
        response = await self.get(url, headers=self._headers)
        return {
            row["asset"]: float(row["free"])
            for row in response["balances"]
        }

    async def fetch_fees(self, symbol):
        endpoint = "/sapi/v1/asset/tradeFee"
        data = {"symbol": symbol.replace("/", "")}
        url = self._get_request_url(endpoint, data=data, timestamp=self._nonce())
        response = await self.get(url, headers=self._headers)

        return {
            "taker": float(response[0]["takerCommission"]),
            "maker": float(response[0]["makerCommission"])
        }

    async def fetch_order_book(self, symbol, **kwargs):
        endpoint = "/api/v3/depth"
        data = {"symbol": symbol.replace("/", "")}
        url = self._get_request_url(endpoint, data=data, signature=False)

        response = await self.get(url, headers=self._headers)

        asks = [[float(x[0]), float(x[1])] for x in response["asks"]]
        bids = [[float(x[0]), float(x[1])] for x in response["bids"]]
        return asks, bids

    async def create_order(self, _id, symbol, qty, price, side):
        endpoint = "/api/v3/order"
        nonce = self._nonce()
        data = {
            "symbol": symbol.replace("/", ""),
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "IOC",
            "quantity": qty,
            "price": price,
            "newClientOrderId": str(_id),
            "timestamp": int(nonce)
        }

        url = self._get_request_url(endpoint, data=data)
        response = await self.post(url, headers=self._headers)

        if response.get("code"):
            self.notify("Error on {} order: {}".format(side, response))
            return False, _id

        self.notify("Exchange order ID", _id)

        return True, _id

    async def cancel_order(self, order_id, symbol=None, *args, **kwargs):
        endpoint = "/api/v3/order"
        data = {
            "symbol": symbol.replace("/", ""),
            "origClientOrderId": order_id,
            "timestamp": int(self._nonce())
        }
        url = self._get_request_url(endpoint, data=data)
        response = await self.delete(url, headers=self._headers)

        if response.get("code"):
            self.notify("Error on cancel order: {}".format(response))
            return False

        return True

    async def fetch_order_status(self, order_id, symbol=None):
        endpoint = "/api/v3/order"
        data = {
            "symbol": symbol.replace("/", ""),
            "origClientOrderId": order_id,
            "timestamp": int(self._nonce())
        }
        url = self._get_request_url(endpoint, data=data)
        response = await self.get(url, headers=self._headers)

        if response.get("code"):
            self.notify("Error status retrieve: {}".format(response))
            return

        filled = response["status"] == "FILLED"
        data = {
            "price": float(response["price"]),
            "base_quantity": float(response["origQty"]),
            "timestamp": datetime.datetime.fromtimestamp(response["time"] / 1000.0),
            "filled": filled,
            "fee": 0.0
        }

        if filled and response["executedQty"] > 0.0:
            data["fee"] = float(response["cummulativeQuoteQty"]) - float(response["executedQty"])
            data["base_quantity"] = float(response["executedQty"]),

        return data

    def _get_request_url(self, endpoint, data=None, timestamp=None, signature=True):
        query_string = ""
        if data is not None:
            query_string = self._get_params_for_sig(data)

        if timestamp is not None and query_string:
            query_string = '{}&timestamp={}'.format(query_string, timestamp)
        elif timestamp is not None and not query_string:
            query_string = 'timestamp={}'.format(timestamp)

        if signature:
            sig = hmac.new(self._secret, query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            return "{}{}?{}&signature={}".format(self._base_url, endpoint, query_string, sig)
        else:
            return "{}{}?{}".format(self._base_url, endpoint, query_string)
