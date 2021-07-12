class MessageBase:
    def __init__(self, *args):
        self.args = args

    def _format(self):
        raise NotImplementedError()

    def __repr__(self):
        return self._format()

    def __str__(self):
        return self._format()


class ExchangeFoundMarkets(MessageBase):
    def _format(self):
        # {Exchange ID} Found {amount of exchange markets} markets
        return f"{self.args[0]}: Found {str(len(self.args[1]))} markets"


class ExchangePreloadMarket(MessageBase):
    def _format(self):
        # {Exchange ID}: Preloading market info for {symbol}"
        return f"{self.args[0]}: Preloading market info for {self.args[1]}"


class ExchangeMarketError(MessageBase):
    def _format(self):
        # {Exchange ID}: Unsuccessful reaching market {symbol}: {error}"
        return f"{self.args[0]}: Unsuccessful reaching market {self.args[1]}: {self.args[2]}"


class ExchangeMarketNoOrderBook(MessageBase):
    def _format(self):
        # {Exchange ID}: No Asks or Bids found for market {symbol}
        return f"No Asks or Bids found for market {self.args[0]}"


class APICreateOrderError(MessageBase):
    def _format(self):
        # {Exchange ID} | {API Class name} - Error on {sell/buy} order: {response}
        return f"{self.args[0]} | {self.args[1]} - Error on {self.args[2]} order: {self.args[3]}"


class APICancelOrderError(MessageBase):
    def _format(self):
        # {Exchange ID} | {API Class name} - Error on cancel order: {response}
        return f"{self.args[0]} | {self.args[1]} - Error on cancel order: {self.args[2]}"


class APIStatusOrderError(MessageBase):
    def _format(self):
        # {Exchange ID} | {API Class name} - Error on retrieve order status: {response}
        return f"{self.args[0]} | {self.args[1]} - Error on retrieve order status: {self.args[2]}"


class APIExchangeOrderId(MessageBase):
    def _format(self):
        # {Exchange ID} - Exchange order ID {order ID}
        return f"{self.args[0]} - Exchange order ID {self.args[1]}"
