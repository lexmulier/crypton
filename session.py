import asyncio
import ssl

import certifi
from aiohttp import TCPConnector, ClientSession


class SessionManager(object):
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        loop = asyncio.get_event_loop()
        context = ssl.create_default_context(cafile=certifi.where())
        connector = TCPConnector(ssl=context, loop=loop, enable_cleanup_closed=False)
        self.client.async_session = ClientSession(loop=loop, connector=connector, trust_env=False)
        await self.client.async_session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb, *args):
        if self.client.async_session:
            return await self.client.async_session.__aexit__(exc_type, exc_val, exc_tb, *args)
