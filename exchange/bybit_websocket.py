import asyncio
import json
import websockets
import aiohttp
from collections import deque
from datetime import datetime, timedelta


class BybitWebsocket:
    def __init__(self, symbols=None):
        """
        Initialize Bybit WebSocket client

        Args:
            symbols (list, optional): List of symbols to subscribe to. If None, all available symbols will be fetched.
        """
        self.symbols = []
        if symbols:
            self.symbols = [symbol.upper() for symbol in symbols]  # Bybit uses uppercase symbols
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"  # Linear (USDT) futures WebSocket URL
        self.rest_api_url = "https://api.bybit.com"
        self.data = {}
        self.volume_data = {}  # 24시간 볼륨 데이터 별도 저장
        self.running = False
        self.websocket = None  # WebSocket 연결 참조 저장
        self.last_volume_update = None  # 마지막 볼륨 업데이트 시간

    async def fetch_all_symbols(self):
        """
        Fetch all available USDT futures trading pairs from Bybit

        Returns:
            list: List of all available USDT futures symbols
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_api_url}/v5/market/instruments-info?category=linear") as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("retCode") == 0 and "result" in data and "list" in data["result"]:
                            # Filter for USDT futures trading pairs that are currently trading
                            symbols = [
                                item["symbol"].upper()
                                for item in data["result"]["list"]
                                if item["symbol"].endswith("USDT") and item["status"] == "Trading"
                            ]
                            print(f"Fetched {len(symbols)} USDT futures trading pairs from Bybit")
                            return symbols
                        else:
                            print(f"Error in Bybit API response: {data}")
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

    # async def send_heartbeat(self):
    #     """Send periodic heartbeat to keep connection alive"""
    #     while self.running and self.websocket:
    #         try:
    #             if not self.websocket.closed:
    #                 heartbeat_message = {"op": "ping"}
    #                 await self.websocket.send(json.dumps(heartbeat_message))
    #                 await asyncio.sleep(20)  # 20초마다 heartbeat
    #             else:
    #                 print("WebSocket connection is closed, stopping heartbeat")
    #                 break
    #         except websockets.exceptions.ConnectionClosed:
    #             print("Connection closed during heartbeat")
    #             break
    #         except Exception as e:
    #             print(f"Error sending heartbeat: {e}")
    #             break


    async def process_messages(self):
        """Process incoming WebSocket messages"""
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                print(f"Bybit WebSocket connection closed: {e}")
                break
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                # websockets.exceptions.ConnectionError 대신 일반적인 연결 오류 처리
                print(f"Bybit WebSocket connection error: {e}")
                break
            except Exception as e:
                print(f"Error in Bybit WebSocket message handling: {e}")
                continue

    async def connect(self):
        """Connect to Bybit WebSocket and subscribe to ticker streams"""
        # If no symbols were provided, fetch all available symbols
        if not self.symbols:
            self.symbols = await self.fetch_all_symbols()

        if not self.symbols:
            print("No symbols available for Bybit. Cannot connect to WebSocket.")
            return

        # 시작할 때 볼륨 데이터 초기 로드
        await self.fetch_24h_volumes()

        # Initialize reconnection parameters
        max_retries = 10000
        retry_count = 0
        base_delay = 1  # Start with 1 second delay
        max_delay = 60  # Maximum delay of 60 seconds

        while self.running or retry_count == 0:
            try:
                self.running = True

                # WebSocket 연결 시 타임아웃 설정
                async with websockets.connect(
                        self.ws_url,
                        ping_interval=20,  # 20초마다 ping
                        ping_timeout=10,  # ping 응답 대기 시간
                        close_timeout=10  # 연결 종료 대기 시간
                ) as websocket:
                    self.websocket = websocket
                    print(f"Connected to Bybit Futures WebSocket for {len(self.symbols)} symbols")

                    retry_count = 0

                    # Bybit has a limit on the number of subscriptions per message
                    # Split into chunks of 10 symbols to avoid exceeding the limit
                    max_symbols_per_subscription = 10
                    symbol_chunks = [self.symbols[i:i + max_symbols_per_subscription] 
                                    for i in range(0, len(self.symbols), max_symbols_per_subscription)]

                    # Subscribe to publicTrade channels for all symbols in chunks
                    for chunk in symbol_chunks:
                        subscription_message = {
                            "op": "subscribe",
                            "args": [f"publicTrade.{symbol}" for symbol in chunk]
                        }
                        await websocket.send(json.dumps(subscription_message))
                        print(f"Subscribed to publicTrade for {len(chunk)} symbols: {chunk[:3]}...")
                        # Small delay to avoid rate limiting
                        await asyncio.sleep(0.1)

                    # Start heartbeat, message processing, and volume update tasks
                    # heartbeat_task = asyncio.create_task(self.send_heartbeat())
                    message_task = asyncio.create_task(self.process_messages())
                    volume_task = asyncio.create_task(self.update_volumes_periodically())

                    try:
                        await asyncio.gather(message_task, volume_task, return_exceptions=True)
                    finally:
                        # 작업 정리
                        for task in [message_task, volume_task]:
                            if not task.done():
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass
                        self.websocket = None


            except websockets.exceptions.ConnectionClosed:
                if not self.running:
                    print("Bybit WebSocket connection closed by user")
                    break
                print("Bybit WebSocket connection closed, attempting to reconnect...")

            except websockets.exceptions.WebSocketException as e:
                print(f"Bybit WebSocket exception: {e}")

            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                print(f"Bybit WebSocket network error: {e}")

            except Exception as e:
                print(f"Bybit WebSocket unexpected error: {e}")

            # 재연결 로직
            if not self.running:
                break

            retry_count += 1
            if retry_count > max_retries:
                print(f"Bybit WebSocket failed to reconnect after {max_retries} attempts. Giving up.")
                break

            # 지수 백오프로 재연결 지연
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"Reconnecting in {delay} seconds... (attempt {retry_count}/{max_retries})")
            await asyncio.sleep(delay)

        print("Bybit WebSocket connection permanently closed")

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
                # print("Received ping, sent pong response")
            return

        # Handle pong messages (response to our ping)
        if 'op' in data and data['op'] == 'pong':
            # print("Received pong response")
            return

        # Handle subscription confirmations
        if 'success' in data and data.get('op') == 'subscribe':
            if data['success']:
                pass
            else:
                print(f"Failed to subscribe: {data}")
            return

        # Handle publicTrade data - 실시간 가격 업데이트
        if 'topic' in data and 'data' in data:
            if data['topic'].startswith('publicTrade.'):
                topic_parts = data['topic'].split('.')
                if len(topic_parts) >= 2:
                    symbol = topic_parts[1]
                    trade_data = data['data']
                    
                    if isinstance(trade_data, list) and trade_data:
                        # Get the latest trade
                        latest_trade = trade_data[-1]
                        price = latest_trade.get('p')  # price
                        # if symbol == 'HFTUSDT':
                        #     print(f"TRADE: {datetime.now()} {symbol} {price}")
                        if price:
                            # 실시간 가격과 저장된 볼륨 데이터 결합
                            volume_usdt_24h = self.volume_data.get(symbol, 0)
                            self.data[symbol] = (float(price), volume_usdt_24h)

    def get_data(self):
        """
        Get current data for all subscribed symbols

        Returns:
            dict: Dictionary of symbol:tuple(price, volume) pairs
        """
        return self.data

    async def stop(self):
        """Stop the WebSocket connection"""
        self.running = False
        if self.websocket:
            await self.websocket.close()