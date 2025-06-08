import time
import requests
import ccxt
import threading
import websocket
import json
import statistics

REPEAT = 10
BYBIT_REST_URL = "https://api.bybit.com"


def benchmark_bybit_rest_all_tickers():
    durations = []
    for _ in range(REPEAT):
        start = time.perf_counter()
        try:
            requests.get(f"{BYBIT_REST_URL}/v5/market/tickers", params={"category": "linear"}).json()
        except Exception as e:
            print(f"❌ REST 오류: {e}")
            continue
        durations.append(time.perf_counter() - start)
    return durations


def benchmark_bybit_ccxt_all_tickers():
    durations = []
    bybit = ccxt.bybit({
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    bybit.load_markets()
    for _ in range(REPEAT):
        start = time.perf_counter()
        try:
            tickers = bybit.fetch_tickers()
            print(tickers)
        except Exception as e:
            print(f"❌ CCXT 오류: {e}")
            continue
        durations.append(time.perf_counter() - start)
    return durations


class BybitWebSocketBenchmark:
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
        print("🌐 WebSocket 연결 중... (Bybit linear ticker stream)")
        self.ws = websocket.WebSocketApp(
            "wss://stream.bybit.com/v5/public/linear",
            on_open=lambda ws: ws.send(json.dumps({
                "op": "subscribe",
                "args": ["tickers.*"]  # or use tickers.* for all
            })),
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


def report(name, durations):
    print(f"📊 {name} ({len(durations)}회)")
    print(f" - 평균: {statistics.mean(durations):.4f}초")
    print(f" - 중앙값: {statistics.median(durations):.4f}초")
    print(f" - 최솟값: {min(durations):.4f}초")
    print(f" - 최댓값: {max(durations):.4f}초")
    print("-" * 40)


if __name__ == "__main__":
    print("🔬 Bybit 전체 티커 벤치마크 (REST vs CCXT vs WebSocket)\n")

    rest_result = benchmark_bybit_rest_all_tickers()
    ccxt_result = benchmark_bybit_ccxt_all_tickers()
    ws_benchmark = BybitWebSocketBenchmark()
    ws_result = ws_benchmark.benchmark()

    print("\n📈 결과 비교")
    report("REST: /v5/market/tickers", rest_result)
    report("CCXT: fetch_tickers()", ccxt_result)
    report("WebSocket: tickers.BTCUSDT 간격", ws_result)
