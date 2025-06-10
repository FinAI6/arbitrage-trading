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

# .env 로드
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET")

# 바이낸스 클라이언트 초기화
client = Client(API_KEY, API_SECRET)
client.sync_time = True

# 거래 설정
symbol = "NXPCUSDT"
buy_price = 1.4
quantity = 10  # 구매 수량

# 시간 기록용 전역 변수
start_dt = None
start_perf_ns = None

def order_buy(symbol, quantity, trigger_price):
    try:
        # 주문 요청 시점의 perf counter
        order_perf_ns = time.perf_counter_ns()

        # 시장가 매수 주문
        order = client.create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        # API에서 주는 체결 시각(ms) → datetime 변환
        transact_ts = order.get("transactTime")  # 밀리초 단위
        order_dt = datetime.fromtimestamp(transact_ts / 1000.0)

        # perf counter 기준 소요 시간
        elapsed_ns = order_perf_ns - start_perf_ns
        elapsed_ms = elapsed_ns / 1_000_000

        # 체결 정보
        fills = order.get("fills", [])
        if fills:
            total_qty = sum(float(f['qty']) for f in fills)
            total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
            avg_price = total_cost / total_qty if total_qty else "N/A"
        else:
            avg_price = "N/A"

        print()
        print("🔽 체결 요약")
        print(f"🔵 가격 수신 시각:  {start_dt.strftime('%H:%M:%S.%f')[:-3]} (실시간 가격: {trigger_price})")
        print(f"🟢 매수 체결 시각:  {order_dt.strftime('%H:%M:%S.%f')[:-3]} (체결 평균가: {avg_price})")
        print(f"✅ 총 소요 시간:    {elapsed_ms:.3f} 밀리초 ({elapsed_ns} ns)")
        print()

    except BinanceAPIException as e:
        print("❌ 매수 주문 실패:", e)

def on_message(ws, message):
    global start_dt, start_perf_ns
    data = json.loads(message)
    k = data['k']

    price = float(k['c'])
    event_ts = data.get('E')  # 이벤트 타임스탬프(ms)

    print(f"실시간 가격: {price}")

    # 최초 가격 수신 시각은 이벤트 타임스탬프로
    if start_dt is None and event_ts is not None:
        start_dt = datetime.fromtimestamp(event_ts / 1000.0)
        start_perf_ns = time.perf_counter_ns()
        print(f"🔵 가격 수신 시작 시각: {start_dt.strftime('%H:%M:%S.%f')[:-3]}")

    if price <= buy_price:
        print(f"📉 {buy_price} 이하로 하락 → 매수 시도")
        order_buy(symbol=symbol, quantity=quantity, trigger_price=price)
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

# 웹소켓 스레드 시작
thread = threading.Thread(target=start_websocket)
thread.start()
