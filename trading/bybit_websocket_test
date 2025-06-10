import os
import json
import time
import statistics
import threading
import websocket
from datetime import datetime
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
import ccxt

# .env 로드
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_SECRET")

symbol = "NXPCUSDT"
buy_price = 1.4
quantity = 4

# REST 클라이언트 (선물 마켓)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

# CCXT 설정
exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {
        'defaultType': 'future'
    },
})

# 결과 저장용
results = {
    "websocket": [],
    "rest": [],
    "ccxt": []
}

### ✅ 매수 함수들
def place_order_rest():
    start = time.perf_counter_ns()
    session.place_order(
        category="linear",
        symbol=symbol,
        side="Buy",
        order_type="Market",
        qty=quantity
    )
    end = time.perf_counter_ns()
    return end - start

def place_order_ccxt():
    start = time.perf_counter_ns()
    exchange.create_market_buy_order(symbol.replace("USDT", "/USDT"), quantity)
    end = time.perf_counter_ns()
    return end - start

def place_order_via_websocket(price):
    global ws_start_ns, ws_start_dt
    start = time.perf_counter_ns()
    session.place_order(
        category="linear",
        symbol=symbol,
        side="Buy",
        order_type="Market",
        qty=quantity
    )
    end = time.perf_counter_ns()
    elapsed_ns = end - ws_start_ns
    print(f"\n🧠 WebSocket 트리거 가격: {price}")
    print(f"🕒 WebSocket 기준 소요시간: {elapsed_ns / 1e6:.3f}ms\n")
    results["websocket"].append(elapsed_ns)
    return elapsed_ns

### ✅ WebSocket 처리
ws_start_ns = None
ws_start_dt = None

def on_message(ws, message):
    global ws_start_ns, ws_start_dt
    data = json.loads(message)
    kline = data.get("data", [])[0]
    price = float(kline["close"])

    if price <= buy_price and len(results["websocket"]) < 5:
        ws_start_dt = datetime.utcnow()
        ws_start_ns = time.perf_counter_ns()
        place_order_via_websocket(price)
        time.sleep(1)
        if len(results["websocket"]) >= 5:
            ws.close()

def on_open(ws):
    print("✅ WebSocket 연결됨")
    params = {"op": "subscribe", "args": [f"kline.1.{symbol}"]}
    ws.send(json.dumps(params))

def run_websocket_trading():
    socket_url = "wss://stream.bybit.com/v5/public/linear"
    ws = websocket.WebSocketApp(socket_url, on_message=on_message, on_open=on_open)
    ws.run_forever()

### ✅ 기타 2가지 방식 반복 실행
def run_repeated_orders(name, func):
    for i in range(5):
        print(f"⏳ {name.upper()} {i+1}/5 주문 중...")
        try:
            ns = func()
            print(f"✅ {name.upper()} 주문 완료: {ns / 1e6:.3f} ms")
            results[name].append(ns)
        except Exception as e:
            print(f"❌ {name.upper()} 주문 실패:", e)
        time.sleep(1)

### ✅ 통계 출력
def print_stats(method):
    times = results[method]
    print(f"\n📊 {method.upper()} 평균: {statistics.mean(times)/1e6:.3f}ms | 최소: {min(times)/1e6:.3f}ms | 최대: {max(times)/1e6:.3f}ms")

### ✅ 실행
if __name__ == "__main__":
    print("🚀 1. WebSocket 방식 시작")
    ws_thread = threading.Thread(target=run_websocket_trading)
    ws_thread.start()
    ws_thread.join()

    print("\n🚀 2. REST API 방식 시작")
    run_repeated_orders("rest", place_order_rest)

    print("\n🚀 3. CCXT 방식 시작")
    run_repeated_orders("ccxt", place_order_ccxt)

    # 결과 출력
    print_stats("websocket")
    print_stats("rest")
    print_stats("ccxt")
