from orders import *
from trade import *
from trade import load_settings_file

# Trade
trade_id = ObjectId("60e1200937b478984144e493")
worker = "binance_kucoin_pols-btc"

# Run
settings = load_settings_file(worker)
exchanges = initiate_exchanges(
    settings["exchanges"],
    preload_market=settings.get("market"),
    exchange_settings=settings["settings"],
    log_level="info",
)
refresh_exchange_balances(0, exchanges)
self = CryptonTrade(
    market=settings["market"],
    exchanges=exchanges,
    min_base_qty=settings.get("min_base_qty"),
    min_quote_qty=settings.get("min_quote_qty"),
    base_precision=settings.get("base_precision"),
    quote_precision=settings.get("quote_precision"),
    log_level="info",
    simulate=False
)

trade = db.client.trades.find_one(trade_id)
ask_exchange = exchanges[trade["ask_exchange"]]
bid_exchange = exchanges[trade["bid_exchange"]]
ask_exchange.balance = trade["expected"]["ask"]["balance"]
bid_exchange.balance = trade["expected"]["bid"]["balance"]
self.ask = BestOrderAsk(ask_exchange.markets[settings["market"]], ask_exchange, trade["expected"]["ask"]["order_book"])
self.bid = BestOrderBid(bid_exchange.markets[settings["market"]], bid_exchange, trade["expected"]["bid"]["order_book"])


