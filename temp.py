###
import asyncio
import aiohttp
import time

async def main(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [session.get(url) for url in urls]
        resp = await asyncio.gather(*tasks)
    return resp


urls = [
    "https://deelay.me/8000/https://google.com",
    "https://deelay.me/3000/https://google.com",
]
start_time = time.time()
loop = asyncio.get_event_loop()
responses = loop.run_until_complete(main(urls))
print("--- %s seconds ---" % (time.time() - start_time))

print(len(responses))



# import requests
# import time
#
# urls = [
#     "https://deelay.me/8000/https://google.com",
#     "https://deelay.me/3000/https://google.com",
# ]
# start_time = time.time()
# for url in urls:
#     requests.get(url)
# print("--- %s seconds ---" % (time.time() - start_time))