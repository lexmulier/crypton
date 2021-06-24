from orders import *
from trade import *

# Trade
trade_id = ObjectId("60d48d7fa81f6886be14592f")

# Settings
verbose = True
market = "MITX/USDT"
exchange_ids = ["ascendex", "kucoin"]
min_profit_perc = None
min_profit_amount = None
min_base_qty = 10.0
min_quote_qty = 5.0

exchanges = initiate_exchanges(exchange_ids, preload_market=market, verbose=verbose)
refresh_exchange_balances(0, exchanges)
self = CryptonTrade(
    market=market,
    exchanges=exchanges,
    min_profit_perc=min_profit_perc,
    min_profit_amount=min_profit_amount,
    min_base_qty=min_base_qty,
    min_quote_qty=min_quote_qty,
    verbose=verbose
)

trade = db.client.trades.find_one(trade_id)
ask_exchange = exchanges[trade["ask_exchange"]]
bid_exchange = exchanges[trade["bid_exchange"]]
ask_exchange.balance = trade["expected"]["ask"]["balance"]
bid_exchange.balance = trade["expected"]["bid"]["balance"]
self.ask = BestOrderAsk(ask_exchange.markets[market], ask_exchange, trade["expected"]["ask"]["order_book"])
self.bid = BestOrderBid(bid_exchange.markets[market], bid_exchange, trade["expected"]["bid"]["order_book"])


