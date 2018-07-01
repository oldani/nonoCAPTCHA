import asyncio
import backoff
import random
import shutil

from aiohttp import web, ClientSession, ClientError
from async_timeout import timeout
from pathlib import Path

from nonocaptcha import util
from nonocaptcha.solver import Solver
from config import settings

proxy_source = settings["proxy_source"]
proxies = None

app = web.Application()


def shuffle(i):
    random.shuffle(i)
    return i


async def work(pageurl, sitekey, proxy):
    # Chromium options and arguments
    options = {"ignoreHTTPSErrors": True, "args": ["--timeout 5"]}
    client = Solver(pageurl, sitekey, options=options, proxy=proxy)
    try:
        result = await client.start()
        if result:
            return result
    except asyncio.CancelledError:
        return


async def get_solution(request):
    while not proxies:
        await asyncio.sleep(1)

    params = request.rel_url.query
    pageurl = params['pageurl']
    sitekey = params['sitekey']
    response = {'error': 'invalid request'}
    if pageurl and sitekey:
        result = None
        async with timeout(3*60) as timer:
            while not timer.expired:
                try:
                    proxy = next(proxies)
                    result = await work(pageurl, sitekey, proxy)
                    if result:
                        break
                except asyncio.CancelledError:
                    break
        if result:
            response = {'solution': result}
        else:
            response = {'error': 'worker timed-out'}
    return web.json_response(response)


async def load_proxies():
    global proxies
    while 1:
        protos = ["http://", "https://"]
        if any(p in proxy_source for p in protos):
            f = util.get_page
        else:
            f = util.load_file
        
        try:
            result = await f(proxy_source)
        except:
            continue
        else:
            proxies = iter(shuffle(result.strip().split("\n")))
            await asyncio.sleep(10*60)


async def start_background_tasks(app):
    app['dispatch'] = app.loop.create_task(load_proxies())


async def cleanup_background_tasks(app):
    app['dispatch'].cancel()
    await app['dispatch']

app.router.add_get('/get', get_solution)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

home = Path.home()
dir = f'{home}/.pyppeteer/.dev_profile'
shutil.rmtree(dir, ignore_errors=True)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=5000)
