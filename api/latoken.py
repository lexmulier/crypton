import datetime
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
            if not base or not quote:
                continue

            symbol = "{}/{}".format(base, quote)
            markets.append({
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "min_base_qty": float(market["minOrderQuantity"]),
                "min_quote_qty": float(market["minOrderCostUsd"]),
                "base_precision": int(market["quantityDecimals"]),
                "quote_precision": int(market["costDisplayDecimals"]),
                "price_precision": int(market["priceDecimals"])
            })
        return markets

    async def fetch_balance(self):
        endpoint = "/v2/auth/account"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {
            self._id_to_coin_mapping.get(row["currency"]): float(row["available"])
            for row in response if self._id_to_coin_mapping.get(row["currency"])
        }

    async def fetch_fees(self, symbol):
        base, quote = symbol.split("/")
        endpoint = "/v2/auth/trade/fee/{}/{}".format(base, quote)
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return {
            "taker": float(response["takerFee"]),
            "maker": float(response["makerFee"])
        }

    async def fetch_order_book(self, symbol, **kwargs):
        base, quote = symbol.split("/")
        endpoint = "/v2/book/{}/{}".format(self._coin_to_id_mapping[base], self._coin_to_id_mapping[quote])
        url = self._base_url + endpoint
        response = await self.get(url)

        asks = [[float(x["price"]), float(x["quantity"])] for x in response["ask"]]
        bids = [[float(x["price"]), float(x["quantity"])] for x in response["bid"]]
        return asks, bids

    async def create_order(self, _id, symbol, qty, price, side):
        endpoint = "/v2/auth/order/place"
        url = self._base_url + endpoint
        base, quote = symbol.split("/")
        nonce = self._nonce()
        data = {
            "clientOrderId": str(_id),
            "side": side.upper(),
            "baseCurrency": self._coin_to_id_mapping[base],
            "quoteCurrency": self._coin_to_id_mapping[quote],
            "condition": "IMMEDIATE_OR_CANCEL",
            "type": "LIMIT",
            "quantity": str(qty),
            "price": str(price),
            "timestamp": nonce
        }

        headers = self._get_headers(endpoint, method="POST", data=data)

        compact_data = self._compact_json_dict(data)
        response = await self.post(url, data=compact_data, headers=headers)

        if response.get("status") != "SUCCESS":
            self.log.info("Error on {} order: {}".format(side, response))
            return False, response

        exchange_order_id = response["id"]
        self.log.info("Exchange order ID", exchange_order_id)

        return True, exchange_order_id

    async def cancel_order(self, order_id, *args, **kwargs):
        endpoint = "/v2/auth/order/cancel"
        url = self._base_url + endpoint
        data = {"id": order_id}
        headers = self._get_headers(endpoint, method="POST", data=data)
        compact_data = self._compact_json_dict(data)
        response = await self.post(url, data=compact_data, headers=headers)

        if response.get("status") != "SUCCESS":
            self.log.info("Error on cancel order: {}".format(response))
            return False

        return True

    async def fetch_order_status(self, order_id, **kwargs):
        endpoint = "/v2/auth/order/getOrder/{}".format(order_id)
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)

        filled = response["status"] == "ORDER_STATUS_CLOSED"
        return {
            "price": float(response["price"]),
            "base_quantity": float(response["quantity"]),
            "fee": None,
            "timestamp": datetime.datetime.fromtimestamp(response["timestamp"] / 1000.0),
            "filled": filled
        }

    async def fetch_order_history(self, *args, **kwargs):
        endpoint = "/v2/auth/order"
        url = self._base_url + endpoint
        headers = self._get_headers(endpoint)
        response = await self.get(url, headers=headers)
        return response

    def _get_headers(self, endpoint, method="GET", data=None):
        data_str = self._get_params_for_sig(data) if data else ""

        sig = hmac.new(self._secret, (method + endpoint + data_str).encode("ascii"), hashlib.sha512).hexdigest()

        headers = {
            "X-LA-APIKEY": self._api_key,
            "X-LA-SIGNATURE": sig,
            "X-LA-DIGEST": "HMAC-SHA512"
        }

        return headers
