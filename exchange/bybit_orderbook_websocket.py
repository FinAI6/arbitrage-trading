import asyncio
import json
import websockets
import aiohttp
import sys
from collections import deque
from datetime import datetime, timedelta
from typing import Optional


class BybitOrderbookWebsocket:
    def __init__(self, symbols=None, test_duration=None):
        """
        Initialize Bybit Orderbook WebSocket client

        Args:
            symbols (list): List of symbols to subscribe to. If None, fetches all available symbols
            test_duration (int): Test duration in seconds. If provided, connection will auto-stop after this time
        """
        self.symbols = symbols or []
        self.test_duration = test_duration
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.rest_api_url = "https://api.bybit.com"
        self.data = {}  # Dictionary to store symbol:(bid_price, ask_price, bid_qty, ask_qty, volume_24h) data
        self.volume_data = {}  # 24시간 볼륨 데이터 별도 저장
        self.running = False
        self.websocket = None
        self.start_time = None
        self.last_volume_update = None  # 마지막 볼륨 업데이트 시간

    async def fetch_all_symbols(self):
        """
        Fetch all available USDT futures trading pairs from Bybit

        Returns:
            list: List of symbol names
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Bybit V5 API endpoint for linear futures
                async with session.get('https://api.bybit.com/v5/market/instruments-info?category=linear') as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('retCode') == 0:
                            symbols = [
                                instrument['symbol']
                                for instrument in data['result']['list']
                                if (instrument['status'] == 'Trading' and 
                                    instrument['symbol'].endswith('USDT') and
                                    instrument['contractType'] == 'LinearPerpetual')
                            ]
                            print(f"Fetched {len(symbols)} USDT futures trading pairs from Bybit")
                            return symbols
                        else:
                            print(f"Error fetching Bybit futures symbols: {data.get('retMsg', 'Unknown error')}")
                            return []
                    else:
                        print(f"Error fetching Bybit futures symbols: HTTP {response.status}")
                        return []
        except Exception as e:
            print(f"Error fetching Bybit futures symbols: {e}")
            return []

    async def fetch_24h_volumes(self):
        """
        Fetch 24-hour volume data for all symbols via REST API
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_api_url}/v5/market/tickers?category=linear") as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("retCode") == 0 and "result" in data and "list" in data["result"]:
                            volume_updates = 0
                            for item in data["result"]["list"]:
                                symbol = item.get("symbol")
                                if symbol in self.symbols:
                                    volume_24h = float(item.get("volume24h", 0))
                                    turnover_24h = float(item.get("turnover24h", 0))  # USDT 기준 거래대금

                                    # turnover24h가 이미 USDT 기준이므로 바로 사용
                                    self.volume_data[symbol] = turnover_24h
                                    volume_updates += 1

                            print(f"Updated 24h volume data for {volume_updates} symbols")
                            self.last_volume_update = datetime.now()
                        else:
                            print(f"Error in Bybit volume API response: {data}")
                    else:
                        print(f"Error fetching Bybit 24h volumes: HTTP {response.status}")
        except Exception as e:
            print(f"Error fetching Bybit 24h volumes: {e}")

    async def update_volumes_periodically(self):
        """
        Periodically update 24-hour volume data (every 24 hours)
        """
        while self.running:
            try:
                # 첫 실행이거나 24시간이 지났으면 볼륨 데이터 업데이트
                if (self.last_volume_update is None or 
                    datetime.now() - self.last_volume_update > timedelta(hours=24)):
                    await self.fetch_24h_volumes()

                # 24시간마다 체크 (실제로는 1시간마다 체크해서 정확성 향상)
                await asyncio.sleep(3600)  # 1시간마다 체크
            except Exception as e:
                print(f"Error in volume update task: {e}")
                await asyncio.sleep(3600)  # 에러가 발생해도 1시간 후 재시도

    async def process_messages(self):
        """Process incoming WebSocket messages"""
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                print(f"Bybit OrderBook WebSocket connection closed: {e}")
                break
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                print(f"Bybit OrderBook WebSocket connection error: {e}")
                break
            except Exception as e:
                print(f"Error in Bybit OrderBook WebSocket message handling: {e}")
                continue

    async def _monitor_test_duration(self):
        """Monitor test duration and stop connection when time limit is reached"""
        if not self.test_duration:
            return

        while self.running:
            if self.start_time and (datetime.now() - self.start_time).total_seconds() >= self.test_duration:
                print(f"Test duration of {self.test_duration} seconds reached. Stopping connection...")
                await self.stop()
                break
            await asyncio.sleep(1)

    async def connect(self):
        """Connect to Bybit WebSocket and subscribe to orderbook streams"""
        # Record start time for test duration
        self.start_time = datetime.now()

        # If no symbols were provided, fetch all available symbols
        if not self.symbols:
            self.symbols = await self.fetch_all_symbols()

        if not self.symbols:
            print("No symbols available for Bybit. Cannot connect to WebSocket.")
            return

        # 시작할 때 볼륨 데이터 초기 로드
        await self.fetch_24h_volumes()

        self.running = True
        backoff = 1

        while self.running:
            try:
                print(f"[Bybit] Attempting connection... (attempt {retry_count + 1})")

                # WebSocket connection with improved timeout settings
                async with websockets.connect(
                        self.ws_url,
                        ping_interval=20,  # Send ping every 20 seconds
                        ping_timeout=10,  # Wait 10 seconds for ping response
                        close_timeout=10,  # Wait 10 seconds for connection close
                        compression=None,  # Disable compression for stability
                        max_size=10**7,    # Increase max message size
                        read_limit=10**7   # Increase read buffer size
                ) as websocket:
                    self.websocket = websocket
                    print(f"✅ [Bybit] Connected successfully for {len(self.symbols)} symbols")

                    retry_count = 0  # Reset retry count on successful connection

                    # Subscribe to orderbook channels
                    await self._subscribe_to_orderbook(websocket)

                    # Start message processing, volume update, and test duration monitoring tasks
                    message_task = asyncio.create_task(self.process_messages())
                    volume_task = asyncio.create_task(self.update_volumes_periodically())
                    tasks = [message_task, volume_task]

                    if self.test_duration:
                        duration_task = asyncio.create_task(self._monitor_test_duration())
                        tasks.append(duration_task)

                    # 첫 번째 예외 발생 시 반환
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_EXCEPTION
                    )

                    # 예외가 있으면 raise → 외부 except로 이동
                    for d in done:
                        exc = d.exception()
                        if exc:
                            raise exc

            except (websockets.ConnectionClosed, asyncio.TimeoutError, OSError) as e:
                print(f"Bybit OrderBook WebSocket connection closed: {e}")
                # 남아있는 태스크 정리
                for t in pending:
                    t.cancel()
                # 지수형 back-off 후 재접속
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue  # while self.running

            except asyncio.CancelledError:
                # 외부 stop()
                break

            finally:
                self.websocket = None

        print("Bybit websocket loop stopped.")

    async def _subscribe_to_orderbook(self, websocket):
        """Subscribe to orderbook channels"""
        max_symbols_per_subscription = 10
        symbol_chunks = [self.symbols[i:i + max_symbols_per_subscription] 
                        for i in range(0, len(self.symbols), max_symbols_per_subscription)]

        for chunk in symbol_chunks:
            subscription_message = {
                "op": "subscribe",
                "args": [f"orderbook.1.{symbol}" for symbol in chunk]
            }
            await websocket.send(json.dumps(subscription_message))
            print(f"📡 [Bybit] Subscribed to {len(chunk)} symbols")
            await asyncio.sleep(0.1)  # Prevent rate limiting

    async def handle_message(self, message):
        """
        Process incoming WebSocket messages

        Args:
            message (str): JSON message from WebSocket
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            print(f"Invalid JSON received: {message}")
            return

        # Handle ping messages - respond with pong
        if 'op' in data and data['op'] == 'ping':
            if self.websocket:
                pong_message = {'op': 'pong', 'args': data.get('args', [])}
                await self.websocket.send(json.dumps(pong_message))
            return

        # Handle pong messages (response to our ping)
        if 'op' in data and data['op'] == 'pong':
            return

        # Handle subscription confirmations
        if 'success' in data and data.get('op') == 'subscribe':
            if data['success']:
                pass
            else:
                print(f"Failed to subscribe: {data}")
            return

        # Handle orderbook.1 data - real-time best bid/ask updates
        if 'topic' in data and 'data' in data:
            if data['topic'].startswith('orderbook.1.'):
                topic_parts = data['topic'].split('.')
                if len(topic_parts) >= 3:
                    symbol = topic_parts[2]
                    orderbook_data = data['data']

                    # Extract best bid and ask from orderbook data
                    # Bybit orderbook.1 format: {"b": [["price", "qty"]], "a": [["price", "qty"]]}
                    if 'b' in orderbook_data and 'a' in orderbook_data:
                        bids = orderbook_data['b']
                        asks = orderbook_data['a']

                        if bids and asks and len(bids[0]) >= 2 and len(asks[0]) >= 2:
                            bid_price = float(bids[0][0])  # Best bid price
                            bid_qty = float(bids[0][1])    # Best bid quantity
                            ask_price = float(asks[0][0])  # Best ask price
                            ask_qty = float(asks[0][1])    # Best ask quantity

                            # 실시간 오더북 데이터와 저장된 볼륨 데이터 결합
                            volume_usdt_24h = self.volume_data.get(symbol, 0)

                            ws_timestamp = data.get('ts')

                            # Store as (bid_price, ask_price, bid_qty, ask_qty, volume_24h)
                            self.data[symbol] = (bid_price, ask_price, bid_qty, ask_qty, volume_usdt_24h, ws_timestamp)

                            # Optional: Print sample data for debugging
                            # if symbol == 'CHILLGUYUSDT':
                            #     print(f"ORDERBOOK: {datetime.now()} {symbol} Bid: {bid_price} Ask: {ask_price}")

    def get_data(self):
        """
        Get current orderbook data for all subscribed symbols

        Returns:
            dict: Dictionary of symbol:(bid_price, ask_price, bid_qty, ask_qty, volume_24h) tuples
        """
        return self.data

    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    async def stop(self):
        """Stop the WebSocket connection"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        print("Bybit OrderBook WebSocket stopping...")


# Test function
async def test_bybit_orderbook_websocket(test_duration=30):
    """
    Test Bybit OrderBook WebSocket connection

    Args:
        test_duration (int): Test duration in seconds
    """
    print(f"Starting Bybit OrderBook WebSocket test for {test_duration} seconds...")

    # Test with a few popular symbols
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']

    websocket_client = BybitOrderbookWebsocket(symbols=test_symbols, test_duration=test_duration)

    try:
        await websocket_client.connect()

        # Print final data summary
        data = websocket_client.get_data()
        print(f"\nTest completed. Received data for {len(data)} symbols:")
        for symbol, (bid_price, ask_price, bid_qty, ask_qty, volume_24h) in list(data.items())[:10]:  # Show first 10
            spread = ask_price - bid_price
            spread_pct = (spread / bid_price) * 100 if bid_price > 0 else 0
            print(f"{symbol}: Bid={bid_price:.6f} Ask={ask_price:.6f} Spread={spread:.6f} ({spread_pct:.4f}%) Volume24h={volume_24h:.2f}USDT")

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        await websocket_client.stop()


if __name__ == "__main__":
    # Run test for 30 seconds
    if sys.platform == 'win32':
        # SelectorEventLoop로 강제로 설정
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_bybit_orderbook_websocket(30))