import datetime
import matplotlib.pyplot as plt
import io
import aiohttp
import asyncio
import json
import websockets
from aiogram import html
from collections import defaultdict
from time import time

BASE_URL = "https://api.binance.com"
WS_URL = "wss://stream.binance.com:9443/ws"

BINANCE_INTERVALS = {
    'd': '1d',
    'h': '1h',
    'm': '1m'
}

price_cache = defaultdict(lambda: {'price': None, 'timestamp': 0})
subscriptions = set()
CACHE_TIMEOUT = 60

async def websocket_manager():
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                while True:
                    if subscriptions:
                        subscribe_msg = {
                            "method": "SUBSCRIBE",
                            "params": [f"{ticker.lower()}usdc@ticker" for ticker in subscriptions],
                            "id": 1
                        }
                        await ws.send(json.dumps(subscribe_msg))
                    message = await ws.recv()
                    data = json.loads(message)
                    if 's' in data and 'c' in data:
                        symbol = data['s'].replace('USDC', '').upper()
                        if symbol in subscriptions:
                            price = float(data['c'])
                            price_cache[symbol] = {'price': price, 'timestamp': time()}
        except Exception:
            await asyncio.sleep(5)

async def subscribe_ticker(ticker: str):
    ticker = ticker.upper()
    if ticker not in subscriptions:
        subscriptions.add(ticker)
        price_cache[ticker] = {'price': None, 'timestamp': 0}

async def unsubscribe_ticker(ticker: str):
    ticker = ticker.upper()
    subscriptions.discard(ticker)
    price_cache.pop(ticker, None)

async def get_current_price(tickers: list, currency: str = 'USDC', force_refresh: bool = False):
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = [ticker.upper() for ticker in tickers]
    for ticker in tickers:
        await subscribe_ticker(ticker)
    result = {}
    missing = []
    current_time = time()
    for ticker in tickers:
        cache = price_cache.get(ticker, {'price': None, 'timestamp': 0})
        if not force_refresh and cache['price'] is not None and (current_time - cache['timestamp']) < CACHE_TIMEOUT:
            result[ticker] = cache['price']
        else:
            missing.append(ticker)
            price_cache[ticker] = {'price': None, 'timestamp': 0}
    if missing:
        symbols = [f"{ticker}{currency.upper()}" for ticker in missing]
        url = f"{BASE_URL}/api/v3/ticker/price"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return {ticker: None for ticker in tickers}, f"Error fetching prices: HTTP {response.status}"
                    data = await response.json()
                    price_map = {item['symbol']: float(item['price']) for item in data}
                    for ticker, symbol in zip(missing, symbols):
                        if symbol in price_map:
                            result[ticker] = price_map[symbol]
                            price_cache[ticker] = {'price': price_map[symbol], 'timestamp': current_time}
                        else:
                            usdt_symbol = f"{ticker}USDT"
                            if usdt_symbol in price_map:
                                result[ticker] = price_map[usdt_symbol]
                                price_cache[ticker] = {'price': price_map[usdt_symbol], 'timestamp': current_time}
                            else:
                                result[ticker] = None
                    return result, None
        except Exception as e:
            return {ticker: None for ticker in tickers}, f"Error retrieving prices: {str(e)}"
    return result, None

async def get_crypto_price(ticker: str, time_period: str, currency: str = 'USDC'):
    unit = time_period[-1].lower()
    if unit not in BINANCE_INTERVALS:
        return None, f"Invalid time unit. Use {html.bold('d')}, {html.bold('h')}, or {html.bold('m')} (e.g., {html.code('7d')})"
    try:
        value = int(time_period[:-1])
    except ValueError:
        return None, f"Invalid time value. Use format like {html.code('7d')}, {html.code('12h')}"
    interval = BINANCE_INTERVALS[unit]
    symbol = ticker.upper() + currency.upper()
    limit = value
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None, f"Error fetching data for {html.bold(ticker)}"
                data = await response.json()
    except Exception as e:
        return None, f"Error requesting from Binance: {str(e)}"
    if not data:
        return None, f"No data for {html.bold(ticker)} for the specified period."
    dates = [datetime.datetime.fromtimestamp(candle[0] / 1000) for candle in data]
    prices = [float(candle[4]) for candle in data]
    plt.figure(figsize=(10, 5))
    plt.plot(dates, prices, label=f'{ticker.upper()} Price')
    plt.xlabel('Date')
    plt.ylabel(f'Price ({currency.upper()})')
    plt.title(f'{ticker.upper()} for {time_period}')
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png')
    img_buffer.seek(0)
    plt.close()
    return img_buffer, None