import asyncio
import datetime
import json
import os

from models import db


def load_settings_file(worker):
    filename = worker if worker[-4:] == "json" else worker + ".json"
    filename = os.path.join("trader", "workers", filename)

    if filename is None or not os.path.exists(filename):
        raise ImportError("No settings file is provided or file does not exist!")

    config_file = open(filename).read()
    settings = json.loads(config_file)

    return settings


def refresh_exchange_balances(counter, exchanges):
    if counter % 10000 == 0:
        update_local_balances_from_exchanges(exchanges)
    if counter % 1000 == 0:
        for exchange in exchanges.values():
            exchange.get_balance(from_database=True)


def update_local_balances_from_exchanges(exchanges):
    loop = asyncio.get_event_loop()
    tasks = [exchange.retrieve_balance() for exchange in exchanges.values()]
    loop.run_until_complete(asyncio.gather(*tasks))


def upsert_market_pair(market, exchanges):
    market_pair_id = "_".join([*sorted(exchanges), market]).upper()

    timestamp = datetime.datetime.now()
    market_pair_info = {
        "market_pair_id": market_pair_id,
        "exchanges": exchanges,
        "market": market,
        "last_run": timestamp
    }
    db.client.market_pairs.update_one(
        {"market_pair_id": market_pair_id},
        {"$set": market_pair_info, "$setOnInsert": {"first_run": timestamp}},
        upsert=True
    )
    return market_pair_id