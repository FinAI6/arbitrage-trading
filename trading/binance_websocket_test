import os
import json
import threading
import websocket
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import ccxt
import requests
import hmac
import hashlib
import urllib.parse
import statistics

# .env 로드
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET")

# Binance SDK 클라이언트
client = Client(API_KEY, API_SECRET)
client.sync_time = True

# 거래 설정
symbol = "NXPCUSDT"
buy_price = 1.4
quantity = 4

# ccxt 인스턴스
ccxt_binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

BASE_URL = "https://api.binance.com"

# 단일 주문 함수들
def order_sdk(symbol, quantity):
    start = time.perf_counter_ns()
    try:
        client.create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        return time.perf_counter_ns() - start
    except Exception:
        return None

def order_ccxt(symbol, quantity):
    start = time.perf_counter_ns()
    try:
        ccxt_binance.create_market_buy_order(symbol, quantity)
        return time.perf_counter_ns() - start
    except Exception:
        return None

def order_rest(symbol, quantity):
    start = time.perf_counter_ns()
    try:
        timestamp = int(time.time() * 1000)
        query = {
            'symbol': symbol,
            'side': 'BUY',
            'type': 'MARKET',
            'quantity': quantity,
            'timestamp': timestamp
        }
        query_string = urllib.parse.urlencode(query)
        signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        query['signature'] = signature
        headers = {"X-MBX-APIKEY": API_KEY}
        response = requests.post(f"{BASE_URL}/api/v3/order", headers=headers, params=query)
        response.raise_for_status()
        return time.perf_counter_ns() - start
    except Exception:
        return None

# 성능 테스트 함수
def repeat_order_test(order_fn, label, repeat=10):
    durations = []
    for _ in range(repeat):
        elapsed = order_fn(symbol, quantity)
        if elapsed is not None:
            durations.append(elapsed / 1_000_000)  # ns → ms
        time.sleep(0.3)  # 약간의 간격

    if durations:
        print(f"\n📊 {label} - {len(durations)}회 주문 결과:")
        print(f"▶ 평균 시간: {statistics.mean(durations):.3f} ms")
        print(f"▶ 최소 시간: {min(durations):.3f} ms")
        print(f"▶ 최대 시간: {max(durations):.3f} ms")
    else:
        print(f"\n❌ {label} - 전부 실패")

# 웹소켓 수신 시 10회 반복 주문 및 비교
def on_message(ws, message):
    data = json.loads(message)
    price = float(data['k']['c'])
    if price <= buy_price:
        print(f"\n💰 가격 {price} 감지됨 → 10회 주문 비교 시작")

        repeat_order_test(order_sdk, "Websocket")
        repeat_order_test(order_rest, "REST API")
        repeat_order_test(order_ccxt, "CCXT")

        ws.close()

def on_open(ws):
    print("✅ 웹소켓 연결됨")
    param = {
        "method": "SUBSCRIBE",
        "params": [f"{symbol.lower()}@kline_1m"],
        "id": 1
    }
    ws.send(json.dumps(param))

def start_websocket():
    socket_url = "wss://stream.binance.com:9443/ws"
    ws = websocket.WebSocketApp(socket_url,
                                 on_message=on_message,
                                 on_open=on_open)
    ws.run_forever()

# 웹소켓 시작
threading.Thread(target=start_websocket).start()
