import asyncio
import datetime

from api.ccxt import CcxtAPI
from config import EXCHANGES
from models import db
from session import SessionManager
from api.get_client import API_CLASS_MAPPING


async def fetch_and_update_balance(exchange_id, config):
    client_class = API_CLASS_MAPPING.get(exchange_id, CcxtAPI)
    client = client_class(config, exchange_id=exchange_id)

    async with SessionManager(client):
        # try:
        balance = await client.fetch_balance()
        # except Exception as error:
        #     print(error)
        #     return

    if not balance:
        return

    db.client.balance_current.update_one(
        {"exchange": exchange_id},
        {"$set": {f"balance.{coin}": available for coin, available in balance.items()}},
        upsert=True
    )
    timestamp = datetime.datetime.now()
    history = [
        {"balance": available, "coin": coin, "exchange": exchange_id, "timestamp": timestamp}
        for coin, available in balance.items()
    ]
    db.client.balance_history.insert_many(history)


def update_balances():
    loop = asyncio.get_event_loop()
    tasks = [fetch_and_update_balance(exchange_id, config) for exchange_id, config in EXCHANGES.items()]
    loop.run_until_complete(asyncio.gather(*tasks))


if __name__ == "__main__":
    update_balances()
