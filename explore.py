import argparse
import datetime
import asyncio
import itertools
import logging

from api.coinmarketcap import CoinMarketCapAPI
from exchanges import initiate_exchanges
from log import CryptonLogger
from models import db

logger = logging.getLogger(__name__)

ALL_EXCHANGES = [
    'aax',
    'aofex',
    'bequant',
    'bibox',
    'bigone',
    'binancecoinm',
    'binanceus',
    'binanceusdm',
    'bit2c',
    'bitbank',
    'bitbay',
    'bitcoincom',
    'bitfinex',
    'bitfinex2',
    'bitflyer',
    'bitforex',
    'bitget',
    'bithumb',
    'bitmart',
    'bitmex',
    'bitpanda',
    'bitso',
    'bitstamp',
    'bitstamp1',
    'bittrex',
    'bitvavo',
    'bitz',
    'bl3p',
    'btcalpha',
    'btcbox',
    'btcmarkets',
    'btctradeua',
    'btcturk',
    'bw',
    'bybit',
    'bytetrade',
    'cdax',
    'cex',
    'coinbaseprime',
    'coinbasepro',
    'coincheck',
    'coinex',
    'coinfalcon',
    'coinfloor',
    'coinmate',
    'coinone',
    'coinspot',
    #'crex24',
    'currencycom',
    'delta',
    #'deribit',  # System maintenance
    'digifinex',
    'equos',
    'exmo',
    'exx',
    'ftx',
    'gateio',
    'gemini',
    'gopax',
    'hbtc',
    'hitbtc',
    'hollaex',
    'huobijp',
    'huobipro',
    'idex',
    'independentreserve',
    'indodax',
    'itbit',
    'kuna',
    'lbank',
    'luno',
    'lykke',
    'mercado',
    'mixcoins',
    'ndax',
    'novadax',
    'oceanex',
    'okcoin',
    'okex',
    'okex5',
    'paymium',
    'phemex',
    'poloniex',
    'probit',
    'qtrade',
    'southxchange',
    'stex',
    'therock',
    'tidex',
    'timex',
    'upbit',
    'vcc',
    'wavesexchange',
    'whitebit',
    'xena',
    'zaif',
    'zb',
    'liquid',
    'timex',
    'ascendex',
    'latoken',
    'kucoin',
    'kraken',
    'binance',
    'dextrade',
    'indoex'
]


class CryptonExplore(object):
    MIN_ARBITRAGE_PERCENTAGE = 0.5
    MIN_ARBITRAGE_AMOUNTS = {
        "USDT": 0.05,
        "BTC": 0.000002,
        "ETH": 0.00000233
    }
    DEFAULT_FEE = 0.002

    def __init__(self, exchange_ids, max_base_rank=500, max_quote_rank=50):
        self.exchanges = initiate_exchanges(exchange_ids, auth_endpoints=False)

        self.max_base_rank = max_base_rank
        self.max_quote_rank = max_quote_rank

        self.log = logging.LoggerAdapter(logger, {"module_fields": "EXPLORER"})
        self.coin_data = CoinMarketCapAPI().fetch_coin_info()

    @property
    def markets(self):
        all_markets = set([market for exchange in self.exchanges.values() for market in exchange.market_symbols])

        markets = []
        for market in all_markets:
            if "/" not in market:
                continue

            base, quote = market.split("/")

            if base not in self.coin_data or quote not in self.coin_data:
                continue

            if self.coin_data[base]["rank"] > self.max_base_rank:
                continue

            if self.coin_data[quote]["rank"] > self.max_quote_rank:
                continue

            markets.append(market)

        return markets

    @staticmethod
    def _fetch_orders(exchanges, market):
        loop = asyncio.get_event_loop()
        tasks = [exchange.markets[market].get_orders() for exchange in exchanges]
        return loop.run_until_complete(asyncio.gather(*tasks))

    def fetch_orders(self, exchanges, market):
        response = self._fetch_orders(exchanges, market)
        results = [x for x in response if x[0]]

        if len(results) <= 1:
            return

        for left_order, right_order in itertools.combinations(results, 2):
            yield [left_order[1], right_order[1]], [left_order[2], right_order[2]]

    @staticmethod
    def get_best_opportunity(best_ask, best_bid):
        # Get the total order we can make while there is still arbitrage
        best_ask.opportunity(best_bid.first_price_with_fee)
        best_bid.opportunity(best_ask.first_price_with_fee)

        # Need to recalculate the quantity based on the result of the lowest exchange/balance
        if best_ask.base_qty > best_bid.base_qty:
            # The bid exchange is dictating the maximum amount, recalculating the ask exchange using the new qty
            best_ask.opportunity(best_bid.first_price_with_fee, max_base_qty=best_bid.base_qty)

        elif best_bid.base_qty > best_ask.base_qty:
            # The ask exchange is dictating the maximum amount, recalculating the bid exchange using the new qty
            best_bid.opportunity(best_ask.first_price_with_fee, max_base_qty=best_ask.base_qty)

    def verify_arbitrage_and_profit(self, best_ask, best_bid):
        """
        When the bid price on one exchange is higher than the ask price on another exchange,
        this is an arbitrage opportunity.
        """
        # Check if the best ask and best bid are on different exchanges.
        if best_ask.exchange_id == best_bid.exchange_id:
            return False, None, None

        # If these lists are empty then there is no arbitrage
        if not best_ask.opportunity_found or not best_bid.opportunity_found:
            return False, None, None

        # Check if the amount or percentage is high enough to take the risk
        adequate_margin, profit_perc, profit_amount = self.adequate_profit(best_ask, best_bid)
        if not adequate_margin:
            return False, None, None

        self.log.info(best_ask)
        self.log.info(best_bid)

        # Notify about the profit
        self.log.info(f"Profit margin: {round(profit_perc, 8)}% | "
                      f"Profit in {best_ask.exchange_market.quote_coin}: {round(profit_amount, 8)}")

        return True, profit_perc, profit_amount

    def adequate_profit(self, best_ask, best_bid):
        """
        Return False if we consider the profit margin not large enough
        """
        if not best_bid.quote_qty or not best_ask.quote_qty:
            return False, None, None

        profit_amount = best_bid.quote_qty - best_ask.quote_qty
        quote_coin = best_bid.exchange_market.quote_coin.upper()
        adequate_margin_amount = profit_amount >= self.MIN_ARBITRAGE_AMOUNTS.get(quote_coin, 0.0)

        profit_perc = (profit_amount / best_bid.quote_qty) * 100.0
        adequate_margin_perc = profit_perc >= self.MIN_ARBITRAGE_PERCENTAGE

        return (adequate_margin_amount and adequate_margin_perc), profit_perc, profit_amount

    def _check_arbitrage(self, exchanges, market):
        timestamp = datetime.datetime.now()

        for best_exchange_asks, best_exchange_bids in self.fetch_orders(exchanges, market):
            best_ask = min(best_exchange_asks, key=lambda x: x.first_price)
            best_bid = max(best_exchange_bids, key=lambda x: x.first_price)

            # Set the fee's to avoid retrieval from API each time
            best_ask.fee_overwrite = self.DEFAULT_FEE
            best_bid.fee_overwrite = self.DEFAULT_FEE

            # Get the total order we can make while there is still arbitrage
            self.get_best_opportunity(best_ask, best_bid)

            arbitrage, profit_perc, profit_amount = self.verify_arbitrage_and_profit(best_ask, best_bid)
            if not arbitrage:
                continue

            self._insert_arbitrage_opportunity(market, best_ask, best_bid, profit_perc, profit_amount, timestamp)

    @staticmethod
    def _insert_arbitrage_opportunity(symbol, ask, bid, profit_perc, profit_amount, timestamp):
        data = {
            "market": symbol,
            "ask_exchange": ask.exchange.exchange_id,
            "bid_exchange": bid.exchange.exchange_id,
            "ask_exchange_asks": [[round(x[0], 8), round(x[1], 8)] for x in ask.order_book],
            "bid_exchange_bids": [[round(x[0], 8), round(x[1], 8)] for x in bid.order_book],
            "profit_perc": profit_perc,
            "profit_amount": profit_amount,
            "ask_first_price": round(ask.first_price, 8),
            "ask_first_price_with_fee": round(ask.first_price_with_fee, 8),
            "ask_first_quantity": ask.first_qty,
            "ask_price": round(ask.price, 8),
            "ask_price_with_fee": round(ask.price_with_fee, 8),
            "ask_base_qty": ask.base_qty,
            "ask_quote_qty": ask.quote_qty,
            "bid_first_price": round(bid.first_price, 8),
            "bid_first_price_with_fee": round(bid.first_price_with_fee, 8),
            "bid_first_quantity": bid.first_qty,
            "bid_price": round(bid.price, 8),
            "bid_price_with_fee": round(bid.price_with_fee, 8),
            "bid_base_qty": bid.base_qty,
            "bid_quote_qty": bid.quote_qty,
            "date": timestamp
        }

        db.client.arbitrage.insert_one(data)

    def start(self):
        while True:
            for market in self.markets:
                exchanges = [x for x in self.exchanges.values() if x.markets.get(market)]
                if len(exchanges) > 1:
                    self.log.info(f"CHECK {' + '.join([x.exchange_id for x in exchanges])}: {market}")
                    self._check_arbitrage(exchanges, market)


def get_exchanges_list(exchanges):
    if not exchanges:
        return ALL_EXCHANGES
    return [x for x in exchanges if x in ALL_EXCHANGES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--exchanges", nargs='*', help="Specify exchanges")
    parser.add_argument("-b", "--maxbaserank", type=int, default=500, help="Maximum base coin rank")
    parser.add_argument("-q", "--maxquoterank", type=int, default=50, help="Maximum quote coin rank")
    args = parser.parse_args()

    CryptonLogger(filename="explorer", level="INFO").initiate()

    exchange_id_list = get_exchanges_list(args.exchanges)

    bot = CryptonExplore(exchange_id_list, max_base_rank=args.maxbaserank, max_quote_rank=args.maxquoterank)
    bot.start()
