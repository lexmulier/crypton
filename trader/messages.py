from messages import MessageBase
from utils import rounder


class ExchangeBalance(MessageBase):
    def _format(self):
        # {bid base exchange qty} {base coin} on BID Exchange {bid exchange ID}
        # {ask quote exchange qty} {quote coin} on BID Exchange {ask exchange ID}
        return (
            f"{rounder(self.args[0])} {self.args[1]} on BID exchange {self.args[2]} | "
            f"{rounder(self.args[3])} {self.args[4]} on ASK exchange {self.args[5]}"
        )


class NotEnoughBalance(MessageBase):
    def _format(self):
        # Not enough {coin} on {exchange ID}: {exchange qty}
        return f"Not enough {self.args[0]} on {self.args[1]}. Balance: {rounder(self.args[2])}"


class TakingQuantityFrom(MessageBase):
    def _format(self):
        # Taking quantity from {BID/ASK}: {quantity} {coin}
        return f"Taking quantity from {self.args[0]}: {rounder(self.args[1])} {self.args[2]}"


class ArbitrageSameExchange(MessageBase):
    def _format(self):
        return "Skipping: ASK and BID are on the same exchange"


class NoArbitrage(MessageBase):
    def _format(self):
        return "Skipping: No good arbitrage opportunities found"


class BelowMinimalQty(MessageBase):
    def _format(self):
        # Skipping: {coin} Order quantity {quantity} is below min qty ({minimal quantity})
        return f"Skipping: {self.args[0]} Order quantity {rounder(self.args[1])} is below min qty ({self.args[2]})"


class BelowMinProfitPerc(MessageBase):
    def _format(self):
        # Profit percentage {profit percentage}% below min profit {min profit percentage}%
        return f"Profit percentage {rounder(self.args[0])}% below min profit {self.args[1]}%"


class BelowMinProfitAmount(MessageBase):
    def _format(self):
        # Profit amount {profit amount} {quote coin} below min profit {min profit amount} {quote coin}
        return f"Profit amount {rounder(self.args[0])} {self.args[1]} below min profit {self.args[2]} {self.args[1]}"


class OrderProfit(MessageBase):
    def _format(self):
        # Profit margin: {profit percentage}% | Profit in {profit amount}: {quote coin}
        return f"Profit margin: {rounder(self.args[0])}% | Profit in {self.args[1]}: {rounder(self.args[2])}"


class OrderInfo(MessageBase):
    def _format(self):
        # {side} @ {exchange_id}: quantity={quantity} | price={price} | price_with_fee={price_fee} {coin}
        return (
            f"{self.args[0]} @ {self.args[1]}: quantity={self.args[2]} | "
            f"price={self.args[3]} | price_fee={self.args[4]} {self.args[5]}"
        )


class OrderSuccessful(MessageBase):
    def _format(self):
        return "Both orders successful!"


class OrderFailed(MessageBase):
    def _format(self):
        return "Something is wrong! Could not verify if orders are successful"


class StartProcess(MessageBase):
    def _format(self):
        return f"################### {str(self.args[0])}"
