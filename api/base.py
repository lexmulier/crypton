class APIBase(object):

    def __init__(self, exchange, session, *args, **kwargs):
        self.exchange = exchange
        self.config = exchange.api_config
        self.session = session

    async def request(self, url):
        async with self.session.get(url) as response:
            assert response.status == 200
            return await response.json()
