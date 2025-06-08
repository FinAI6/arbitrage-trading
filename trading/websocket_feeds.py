import time
import json
import threading
from datetime import datetime

import websocket
from abc import ABC, abstractmethod
from typing import Callable, Dict, Tuple


class BaseWebSocketPriceFeed(ABC):
    def __init__(self, symbol: str, callback: Callable[[str, float], None] = None, interval: float = 5.0):
        self.symbol = symbol.upper()
        self.callback = callback or self.default_callback
        self.interval = interval
        self.ws = None
        self.thread = None
        self.last_price = None
        self.running = False

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        pass

    @abstractmethod
    def _build_ws_url(self) -> str:
        pass

    @abstractmethod
    def _build_subscribe_message(self) -> str:
        pass

    @abstractmethod
    def _extract_price(self, msg: Dict) -> float:
        pass

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            price = self._extract_price(data)
            self.last_price = price
        except Exception as e:
            print(f"❌ Message parse error: {e}")

    def _on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def _on_close(self, ws, code, reason):
        print(f"WebSocket closed: {code} {reason}")

    def _on_open(self, ws):
        msg = self._build_subscribe_message()
        if msg:
            ws.send(msg)

    def _run(self):
        self.ws = websocket.WebSocketApp(
            self._build_ws_url(),
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open
        )
        self.ws.run_forever()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

        def loop():
            while self.running:
                if self.last_price is not None:
                    self.callback(self.symbol, self.last_price)
                time.sleep(self.interval)

        monitor_thread = threading.Thread(target=loop)
        monitor_thread.daemon = True
        monitor_thread.start()

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join()

    def default_callback(self, symbol: str, price: float):
        now = datetime.now().strftime("[%H:%M:%S]")
        print(f"{now} {self.exchange_name}: {symbol} = {price}")


class BinancePriceFeed(BaseWebSocketPriceFeed):
    @property
    def exchange_name(self) -> str:
        return "Binance"

    def _build_ws_url(self):
        return f"wss://fstream.binance.com/ws/{self.symbol.lower()}@ticker"

    def _build_subscribe_message(self):
        return ""  # Not required for Binance single stream URL

    def _extract_price(self, msg: Dict):
        return float(msg["c"])  # lastPrice


class BybitPriceFeed(BaseWebSocketPriceFeed):
    @property
    def exchange_name(self) -> str:
        return "Bybit"

    def _build_ws_url(self):
        return "wss://stream.bybit.com/v5/public/linear"

    def _build_subscribe_message(self):
        return json.dumps({
            "op": "subscribe",
            "args": [f"tickers.{self.symbol}"]
        })

    def _extract_price(self, msg: Dict):
        if "data" not in msg or not isinstance(msg["data"], dict):
            return None
            # raise ValueError("No usable data")

        data = msg["data"]

        for key in ["lastPrice", "bid1Price", "ask1Price", "markPrice", "indexPrice"]:
            if key in data:
                return float(data[key])

        # 가격이 없으면 None 반환 → 처리 안 함
        return None


class BitgetPriceFeed(BaseWebSocketPriceFeed):
    @property
    def exchange_name(self) -> str:
        return "BITGET"

    def _build_ws_url(self):
        return "wss://ws.bitget.com/v2/ws/public"

    def _build_subscribe_message(self):
        # self.check_configuration()
        return json.dumps({
            "op": "subscribe",
            "args": [
                {
                    "instType": "SPOT",
                    "channel": "ticker",
                    "instId": f"{self.symbol}"  # ex: BTCUSDT_UMCBL
                }
            ]
        })

    def _extract_price(self, msg: dict):
        topic = msg.get("arg", {}).get("channel", "") or msg.get("topic", "")
        data = msg.get("data", [])

        if not data:
            return None  # 초기 빈 데이터 무시

        entry = data[0] if isinstance(data, list) else data

        if topic == "ticker" and "lastPr" in entry:
            return float(entry["lastPr"])
        if topic.startswith("trade") and "price" in entry:
            return float(entry["price"])

        return None  # 유효 필드 없으면 조용히 무시

    # def check_configuration(self):
    #     print(f"🔎 Bitget v2 설정 체크: {self.symbol}")
    #     # if not self.symbol.endswith(("_UMCBL", "_DMCBL", "_SPBL")):
    #     #     raise ValueError(f"❌ [심볼 오류] '{self.symbol}' 는 _UMCBL, _SPBL, _DMCBL 접미사가 필요합니다.")
    #     # print("✅ v2 주소 및 심볼 포맷 정상")


shared_prices: Dict[str, Tuple[float, float]] = {}  # {exchange_name: (price, timestamp)}
price_ready_events: Dict[str, threading.Event] = {
    "BINANCE": threading.Event(),
    "BYBIT": threading.Event(),
    "BITGET": threading.Event()
}
lock = threading.Lock()


def make_callback(exchange_name: str):
    def _callback(symbol: str, price: float):
        with lock:
            shared_prices[exchange_name] = (price, time.time())
            price_ready_events[exchange_name].set()

    return _callback


def print_comparison(prices: dict):
    now = datetime.now().strftime("[%H:%M:%S]")
    exchanges = ["BINANCE", "BYBIT", "BITGET"]
    available = [(ex, prices[ex]) for ex in exchanges if ex in prices]

    if not available:
        print(f"{now} ⛔ 가격 정보 없음")
        return

    avg_price = sum(p for _, p in available) / len(available)

    print(f"{now} 📊 평균가격: ${avg_price:,.2f} → ", end="")
    for ex, price in available:
        diff_pct = (price - avg_price) / avg_price * 100
        print(f"{ex}: {diff_pct:+.2f}%\t", end="")
    print()


def synchronized_loop(interval=5):
    while True:
        # 모든 거래소가 가격을 수신했는지 기다림
        all_ready = all(e.wait(timeout=interval) for e in price_ready_events.values())

        if all_ready:
            with lock:
                # 시간 차 필터링: 수신 간격 1초 이상이면 무시
                timestamps = [ts for _, ts in shared_prices.values()]
                if max(timestamps) - min(timestamps) <= 1.0:
                    # 평균 비교 등 알고리즘 실행
                    prices = {ex: val[0] for ex, val in shared_prices.items()}
                    print_comparison(prices)
                else:
                    print("⚠️ 수신 시점 차이 큼 → 비교 생략")

            # reset events
            for event in price_ready_events.values():
                event.clear()
        else:
            print("⚠️ 일부 거래소 가격 미도착")
        time.sleep(interval)


if __name__ == '__main__':
    # 피드 시작
    interval = 1
    BinancePriceFeed("BTCUSDT", make_callback("BINANCE"), interval=interval).start()
    BybitPriceFeed("BTCUSDT", make_callback("BYBIT"), interval=interval).start()
    bitget_feed = BitgetPriceFeed("BTCUSDT", make_callback("BITGET"), interval=interval).start()

    # 동기화 루프 시작
    threading.Thread(target=synchronized_loop,
                     kwargs={"interval": 1},
                     daemon=True).start()

    # 메인 스레드를 유지 (Ctrl+C 종료 가능)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⛔ 종료 요청됨. 정리 중...")
