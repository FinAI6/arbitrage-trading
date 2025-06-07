"""
🔬 Binance 전체 티커 벤치마크 (REST vs CCXT vs WebSocket)

📈 결과 비교
📊 REST: /fapi/v1/ticker/24hr (10회)
 - 평균: 0.1936초
 - 중앙값: 0.1929초
 - 최솟값: 0.1787초
 - 최댓값: 0.2297초
----------------------------------------
📊 CCXT: fetch_tickers() (10회)
 - 평균: 1.9664초
 - 중앙값: 2.0084초
 - 최솟값: 1.5933초
 - 최댓값: 2.0426초
----------------------------------------
📊 WebSocket: !ticker@arr 간격 (9회)
 - 평균: 0.9985초
 - 중앙값: 1.0037초
 - 최솟값: 0.9615초
 - 최댓값: 1.0101초
----------------------------------------
"""

import time
import requests
import ccxt
import threading
import websocket
import json
import statistics

REPEAT = 10
FAPI_URL = "https://fapi.binance.com"

def benchmark_fapi_all_tickers():
    durations = []
    for _ in range(REPEAT):
        start = time.perf_counter()
        try:
            symbols = requests.get(f"{FAPI_URL}/fapi/v1/exchangeInfo").json()
            prices = requests.get(f"{FAPI_URL}/fapi/v1/ticker/price").json()
            volume = requests.get(f"{FAPI_URL}/fapi/v1/ticker/24hr").json()
        except Exception as e:
            print(f"❌ FAPI 오류: {e}")
            continue
        durations.append(time.perf_counter() - start)
    return durations

def benchmark_ccxt_all_tickers():
    durations = []
    binance = ccxt.binance({
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    binance.load_markets()
    for _ in range(REPEAT):
        start = time.perf_counter()
        try:
            binance.fetch_tickers()
        except Exception as e:
            print(f"❌ CCXT 오류: {e}")
            continue
        durations.append(time.perf_counter() - start)
    return durations

# WebSocket 벤치마크 클래스
class WebSocketAllTickersBenchmark:
    def __init__(self):
        self.count = 0
        self.max_count = REPEAT
        self.durations = []
        self.prev_time = None
        self.ws = None

    def on_message(self, ws, message):
        now = time.perf_counter()
        if self.prev_time:
            self.durations.append(now - self.prev_time)
        self.prev_time = now
        self.count += 1
        if self.count >= self.max_count:
            ws.close()

    def on_error(self, ws, error):
        print(f"❌ WebSocket 오류: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("🔌 WebSocket 연결 종료")

    def run(self):
        print("🌐 WebSocket 연결 중... (전체 ticker 스트림)")
        self.ws = websocket.WebSocketApp(
            "wss://fstream.binance.com/ws/!ticker@arr",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever()

    def benchmark(self):
        thread = threading.Thread(target=self.run)
        thread.start()
        thread.join()
        return self.durations

# 결과 출력
def report(name, durations):
    print(f"📊 {name} ({len(durations)}회)")
    print(f" - 평균: {statistics.mean(durations):.4f}초")
    print(f" - 중앙값: {statistics.median(durations):.4f}초")
    print(f" - 최솟값: {min(durations):.4f}초")
    print(f" - 최댓값: {max(durations):.4f}초")
    print("-" * 40)

if __name__ == "__main__":
    print("🔬 Binance 전체 티커 벤치마크 (REST vs CCXT vs WebSocket)\n")

    fapi_result = benchmark_fapi_all_tickers()
    ccxt_result = benchmark_ccxt_all_tickers()
    ws_benchmark = WebSocketAllTickersBenchmark()
    ws_result = ws_benchmark.benchmark()

    print("\n📈 결과 비교")
    report("REST: /fapi/v1/ticker/24hr", fapi_result)
    report("CCXT: fetch_tickers()", ccxt_result)
    report("WebSocket: !ticker@arr 간격", ws_result)
