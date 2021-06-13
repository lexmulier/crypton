import base64
import hashlib
import hmac
import time

from api.base import APIBase


class KuCoinAPI(APIBase):
    _base_url = "https://api.kucoin.com/api/v1/"

    def __init__(self, exchange, session):
        super(KuCoinAPI, self).__init__(exchange, session)
        self._api_key = self.config["apiKey"]
        self._secret = self.config["secret"].encode('utf-8')
        self._passphrase = self.config["KC-API-PASSPHRASE"].encode('utf-8')
        self._password = self.config["password"]

    @property
    def _encoded_passphrase(self):
        return base64.b64encode(hmac.new(self._secret, self._passphrase, hashlib.sha256).digest())

    def _encoded_signature(self, now, method="GET", location="/api/v1/accounts"):
        return base64.b64encode(
            self._secret,
            str(now) + method + location,
        )

    def _get_headers(self):
        now = str(int(time.time() * 1000))
        return {
            "KC-API-SIGN": self._encoded_signature(now),
            "KC-API-TIMESTAMP": str(now),
            "KC-API-KEY": self._api_key,
            "KC-API-PASSPHRASE": self._encoded_passphrase,
            "KC-API-KEY-VERSION": 2
        }