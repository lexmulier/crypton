import base64
import hashlib
import hmac

from api.base import BaseAPI


class LATokenAPI(BaseAPI):
    _base_url = "https://api.latoken.com"

    def __init__(self, *args, **kwargs):
        super(LATokenAPI, self).__init__(*args, **kwargs)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode()
        self._id_to_coin_mapping = {}
        self._coin_to_id_mapping = {}

    async def fetch_exchange_specifics(self):
        url = self._base_url + "/v2/ticker"
        response = await self.get(url)
        for row in response:
            base, quote = row["symbol"].split("/")
            self._id_to_coin_mapping[row["baseCurrency"]] = base
            self._coin_to_id_mapping[base] = row["baseCurrency"]
            self._id_to_coin_mapping[row["quoteCurrency"]] = quote
            self._coin_to_id_mapping[quote] = row["quoteCurrency"]

    async def fetch_markets(self):
        url = self._base_url + "/v2/pair"
        response = await self.get(url)

        markets = []
        for market in response:
            base = self._id_to_coin_mapping.get(market["baseCurrency"])
            quote = self._id_to_coin_mapping.get(market["quoteCurrency"])
            symbol = "{}/{}".format(base, quote)
            markets.append({
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "min_base_qty": float(market["minOrderQuantity"]),
                "min_quote_qty": float(market["minOrderCostUsd"]),
                "base_precision": float(market["quantityTick"]),
                "quote_precision": float(market["costDisplayDecimals"]),
                "price_precision": float(market["priceDecimals"])
            })
        return markets

    async def fetch_balance(self):
        endpoint = "/v2/auth/account"
        url = self._base_url + endpoint
        headers, _ = self._get_headers_and_data_str(endpoint)
        response = await self.get(url, headers=headers)
        return {
            self._id_to_coin_mapping.get(row["currency"]): float(row["available"])
            for row in response
        }

    async def fetch_fees(self, symbol):
        base, quote = symbol.split("/")
        endpoint = "/v2/auth/trade/fee/{}/{}".format(base, quote)
        url = self._base_url + endpoint
        headers, _ = self._get_headers_and_data_str(endpoint)
        response = await self.get(url, headers=headers)
        return {
            "taker": float(response["takerFee"]),
            "maker": float(response["makerFee"])
        }

    #
    # async def fetch_order_book(self, symbol, limit=None):
    #     url = self._base_url + "/api/v1/market/orderbook/level2_{}?symbol={}".format(
    #         limit or 20, symbol.replace("/", "-")
    #     )
    #     response = await self.get(url)
    #     asks = [[float(x[0]), float(x[1])] for x in response["data"]["asks"]]
    #     bids = [[float(x[0]), float(x[1])] for x in response["data"]["bids"]]
    #     return asks, bids
    #

    #
    #
    # async def create_order(self, _id, symbol, qty, price, side):
    #     endpoint = "/api/v1/orders"
    #     url = self._base_url + endpoint
    #     data = {
    #         "clientOid": str(_id),
    #         "side": side,
    #         "symbol": symbol.replace("/", "-"),
    #         "type": "limit",
    #         "size": str(qty),
    #         "price": str(price),
    #         "timeInForce": "IOC",
    #         "hidden": False,
    #         "iceberg": False,
    #     }
    #
    #     compact_data = self._compact_json_dict(data)
    #     headers = self._get_headers(endpoint, method="POST", compact_data=compact_data)
    #
    #     response = await self.post(url, data=compact_data, headers=headers)
    #
    #     if response.get("code") != "200000":
    #         self.notify("Error on {} order: {}".format(side, response.get("msg", "Error message N/A")))
    #         return False, response
    #
    #     self.notify("Exchange order ID", _id)
    #
    #     return True, _id
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

    def _get_headers_and_data_str(self, endpoint, method="GET", data=None):
        data_str = "?" + self._get_params_for_sig(data) if data else ""

        sig = hmac.new(self._secret, (method + endpoint + data_str).encode("ascii"), hashlib.sha512).hexdigest()

        headers = {
            "X-LA-APIKEY": self._api_key,
            "X-LA-SIGNATURE": sig,
            "X-LA-DIGEST": "HMAC-SHA512"
        }

        return headers, data_str
