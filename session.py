import asyncio
import ssl

import certifi
from aiohttp import TCPConnector, ClientSession

from api.get_client import get_client


class SessionManager(object):
    def __init__(self, exchange):
        self.loop = asyncio.get_event_loop()
        context = ssl.create_default_context(cafile=certifi.where())
        connector = TCPConnector(ssl=context, loop=self.loop, enable_cleanup_closed=True)
        self.session = ClientSession(loop=self.loop, connector=connector, trust_env=False)

        self.exchange = exchange
        exchange.client = get_client(exchange, self.session)

    async def __aenter__(self):
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb, *args):
        if self.session:
            self.exchange.client = None
            return await self.session.__aexit__(exc_type, exc_val, exc_tb, *args)