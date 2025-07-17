import asyncio
import json
import websockets
import aiohttp
import sys
from collections import deque
from datetime import datetime, timedelta
from typing import Optional


class BybitOrderbookWebsocketMulti:
    def __init__(self, symbols=None, test_duration=None):
        """
        Initialize Bybit OrderBook WebSocket client with multi-connection support

        Args:
            symbols (list): List of symbols to subscribe to. If None, fetches all available symbols
            test_duration (int): Test duration in seconds. If provided, connection will stop after this time
        """
        self.symbols = symbols or []
        self.test_duration = test_duration
        self.start_time = None
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.rest_api_url = "https://api.bybit.com"
        self.data = {}  # Store orderbook data: symbol -> (bid_price, ask_price, bid_qty, ask_qty, volume_24h, timestamp)
        self.volume_data = {}  # Store 24h volume data: symbol -> volume_usdt_24h
        self.last_volume_update = None
        self.running = False
        self.connections = []  # Store websocket connections for cleanup
        self.tasks = []  # Store tasks for proper cleanup

    async def fetch_all_symbols(self):
        """
        Fetch all available USDT futures trading pairs from Bybit

        Returns:
            list: List of symbol names
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_api_url}/v5/market/instruments-info?category=linear") as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("retCode") == 0 and "result" in data and "list" in data["result"]:
                            symbols = [
                                item["symbol"] for item in data["result"]["list"]
                                if item["symbol"].endswith("USDT") and 
                                item["status"] == "Trading" and
                                item.get("contractType") == "LinearPerpetual"
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

    async def connect(self):
        """Connect to Bybit WebSocket and subscribe to orderbook streams with multi-connection support"""
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

        # Set running to True at the beginning
        self.running = True

        # Bybit multi-connection: Split into chunks of 50 symbols per connection
        max_symbols_per_connection = 50
        symbol_chunks = [self.symbols[i:i + max_symbols_per_connection] 
                         for i in range(0, len(self.symbols), max_symbols_per_connection)]

        # Create a task for each chunk
        for i, chunk in enumerate(symbol_chunks):
            task = asyncio.create_task(self._connect_to_streams(chunk, i+1))
            self.tasks.append(task)

        # Add volume update task
        volume_task = asyncio.create_task(self.update_volumes_periodically())
        self.tasks.append(volume_task)

        # Add test duration monitoring task if specified
        if self.test_duration:
            monitor_task = asyncio.create_task(self._monitor_test_duration())
            self.tasks.append(monitor_task)

        # Wait for all connections to complete
        try:
            # Using gather with return_exceptions=True to prevent one failed task from causing all to fail
            results = await asyncio.gather(*self.tasks, return_exceptions=True)

            # Check if all connection tasks failed (excluding volume and test duration tasks)
            connection_results = results[:len(symbol_chunks)]
            all_failed = all(isinstance(result, Exception) for result in connection_results)
            if all_failed:
                print("All Bybit OrderBook WebSocket connections failed. Check network connectivity.")

            # Log any exceptions that occurred
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    if i < len(symbol_chunks):
                        print(f"Bybit OrderBook WebSocket connection {i+1} failed with error: {result}")
                    else:
                        print(f"Bybit OrderBook WebSocket task failed with error: {result}")

        except asyncio.CancelledError:
            print("Bybit OrderBook WebSocket connections cancelled")
        except Exception as e:
            print(f"Error managing Bybit OrderBook WebSocket connections: {e}")

        finally:
            # Clean up connections and tasks only if not already cleaned up
            if self.running or self.tasks or self.connections:
                try:
                    await asyncio.wait_for(self._cleanup(), timeout=10.0)
                except asyncio.TimeoutError:
                    print("Warning: Final cleanup timed out")
                except Exception as e:
                    print(f"Error during final cleanup: {e}")

    async def _monitor_test_duration(self):
        """Monitor test duration and stop connection when time limit is reached"""
        if not self.test_duration:
            return

        try:
            while self.running:
                if self.start_time and (datetime.now() - self.start_time).total_seconds() >= self.test_duration:
                    print(f"Test duration of {self.test_duration} seconds reached. Stopping connection...")
                    try:
                        await asyncio.wait_for(self.stop(), timeout=20.0)
                    except asyncio.TimeoutError:
                        print("Warning: Stop operation timed out in monitor")
                        self.running = False  # Force stop
                    except Exception as e:
                        print(f"Error during stop in monitor: {e}")
                        self.running = False  # Force stop
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Test duration monitor cancelled")
        except Exception as e:
            print(f"Error in test duration monitor: {e}")
            self.running = False

    async def _connect_to_streams(self, symbols, connection_id):
        """
        Connect to WebSocket streams for a subset of symbols

        Args:
            symbols (list): List of symbols to subscribe to
            connection_id (int): Connection identifier for logging
        """
        # Initialize reconnection parameters
        max_retries = 10
        retry_count = 0
        base_delay = 1  # Start with 1 second delay
        max_delay = 60  # Maximum delay of 60 seconds

        while self.running or retry_count == 0:
            try:
                # Set running to True at the beginning of connection attempt
                self.running = True

                # WebSocket connection with timeout settings
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,  # Disable built-in ping, we'll handle it manually
                    ping_timeout=None,
                    close_timeout=10,
                    compression=None,
                    max_size=10**7
                ) as websocket:
                    print(f"Connected to Bybit OrderBook WebSocket connection {connection_id} for {len(symbols)} symbols")

                    # Store connection for cleanup
                    self.connections.append(websocket)

                    # Reset retry count on successful connection
                    retry_count = 0

                    # Subscribe to orderbook channels
                    await self._subscribe_to_orderbook(websocket, symbols)

                    # Start ping task for this connection
                    ping_task = asyncio.create_task(self._send_ping_periodically(websocket, connection_id))

                    try:
                        while self.running:
                            try:
                                message = await asyncio.wait_for(websocket.recv(), timeout=10)
                                await self.handle_message(message)
                            except websockets.exceptions.ConnectionClosed as e:
                                print(f"Bybit OrderBook WebSocket connection {connection_id} closed: {e}")
                                break
                            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                                # Network connection error handling
                                print(f"Bybit OrderBook WebSocket connection {connection_id} network error: {e}")
                                break
                            except Exception as e:
                                print(f"Error in Bybit OrderBook WebSocket connection {connection_id} message handling: {e}")
                                # Continue processing other messages if there's an error with one
                                continue
                    finally:
                        # Cancel ping task
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass

            except websockets.exceptions.ConnectionClosed:
                if not self.running:
                    # If we're intentionally stopping, don't try to reconnect
                    print(f"Bybit OrderBook WebSocket connection {connection_id} closed by user")
                    break
                print(f"Bybit OrderBook WebSocket connection {connection_id} closed, attempting to reconnect...")

            except websockets.exceptions.WebSocketException as e:
                print(f"Bybit OrderBook WebSocket connection {connection_id} exception: {e}")
                if not self.running:
                    break

            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                print(f"Bybit OrderBook WebSocket connection {connection_id} network error: {e}")
                if not self.running:
                    break

            except Exception as e:
                print(f"Unexpected error in Bybit OrderBook WebSocket connection {connection_id}: {e}")
                if not self.running:
                    break

            # Reconnection logic
            if not self.running:
                break

            retry_count += 1
            if retry_count > max_retries:
                print(f"Bybit OrderBook WebSocket connection {connection_id} failed to reconnect after {max_retries} attempts. Giving up.")
                break

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"Bybit OrderBook WebSocket connection {connection_id} reconnecting in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
            await asyncio.sleep(delay)

        print(f"Bybit OrderBook WebSocket connection {connection_id} permanently closed for {len(symbols)} symbols")

    async def _send_ping_periodically(self, websocket, connection_id):
        """
        Send ping messages periodically to maintain connection

        Args:
            websocket: WebSocket connection
            connection_id (int): Connection identifier for logging
        """
        while self.running:
            try:
                # Send ping every 20 seconds as recommended by Bybit
                await asyncio.sleep(20)

                if self.running:
                    try:
                        ping_message = {
                            "req_id": f"ping_{connection_id}_{int(datetime.now().timestamp())}",
                            "op": "ping"
                        }
                        await websocket.send(json.dumps(ping_message))
                    except Exception:
                        # Connection is closed or not available
                        break
                    # print(f"Sent ping to connection {connection_id}")

            except websockets.exceptions.ConnectionClosed:
                print(f"Ping task for connection {connection_id} stopped: connection closed")
                break
            except Exception as e:
                print(f"Error sending ping to connection {connection_id}: {e}")
                break

    async def _subscribe_to_orderbook(self, websocket, symbols):
        """
        Subscribe to orderbook channels for given symbols

        Args:
            websocket: WebSocket connection
            symbols (list): List of symbols to subscribe to
        """
        # Subscribe in chunks to avoid rate limiting
        max_symbols_per_subscription = 10
        symbol_chunks = [symbols[i:i + max_symbols_per_subscription] 
                        for i in range(0, len(symbols), max_symbols_per_subscription)]

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
            # Server ping - we should respond with pong
            # Note: This is different from our client ping
            return

        # Handle pong messages (response to our ping)
        if 'op' in data and data['op'] == 'pong':
            # Response to our ping - just acknowledge
            return

        # Handle subscription confirmations
        if 'success' in data and data.get('op') == 'subscribe':
            if data['success']:
                pass  # Subscription successful
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

                            # Store as (bid_price, ask_price, bid_qty, ask_qty, volume_24h, timestamp)
                            self.data[symbol] = (bid_price, ask_price, bid_qty, ask_qty, volume_usdt_24h, ws_timestamp)

    def get_data(self):
        """
        Get current orderbook data for all subscribed symbols

        Returns:
            dict: Dictionary of symbol:(bid_price, ask_price, bid_qty, ask_qty, volume_24h, timestamp) tuples
        """
        return self.data

    def set_symbols(self, symbols):
        """Set symbols to subscribe to"""
        self.symbols = list(symbols)

    async def _cleanup(self):
        """Clean up connections and tasks"""
        print("Starting cleanup process...")

        # Close all connections first
        for i, connection in enumerate(self.connections):
            if connection:
                try:
                    await asyncio.wait_for(connection.close(), timeout=2.0)
                    print(f"Connection {i+1} closed successfully")
                except asyncio.TimeoutError:
                    print(f"Warning: Connection {i+1} close timed out")
                except Exception as e:
                    print(f"Error closing connection {i+1}: {e}")

        # Cancel all tasks
        cancelled_tasks = []
        for i, task in enumerate(self.tasks):
            if not task.done():
                task.cancel()
                cancelled_tasks.append(task)
                print(f"Cancelled task {i+1}")

        # Wait for cancelled tasks to complete with individual timeouts
        if cancelled_tasks:
            print(f"Waiting for {len(cancelled_tasks)} cancelled tasks to complete...")
            for i, task in enumerate(cancelled_tasks):
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except asyncio.CancelledError:
                    print(f"Task {i+1} cancelled successfully")
                except asyncio.TimeoutError:
                    print(f"Warning: Task {i+1} cancellation timed out")
                except Exception as e:
                    print(f"Error during task {i+1} cleanup: {e}")

        # Clear lists
        self.connections.clear()
        self.tasks.clear()
        print("Cleanup process completed")

    async def stop(self):
        """Stop the WebSocket connection"""
        if not self.running:
            print("Already stopped or stopping...")
            return

        print("Bybit OrderBook WebSocket Multi-Connection stopping...")
        self.running = False

        try:
            await asyncio.wait_for(self._cleanup(), timeout=15.0)
        except asyncio.TimeoutError:
            print("Warning: Stop operation timed out during cleanup")
        except Exception as e:
            print(f"Error during stop operation: {e}")

        print("Stop operation completed")


# Test function
async def test_bybit_orderbook_websocket_multi(test_duration=30):
    """
    Test Bybit OrderBook WebSocket Multi-Connection

    Args:
        test_duration (int): Test duration in seconds
    """
    print(f"Starting Bybit OrderBook WebSocket Multi-Connection test for {test_duration} seconds...")

    # Test with a few popular symbols
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']

    websocket_client = BybitOrderbookWebsocketMulti(symbols=test_symbols, test_duration=test_duration)

    try:
        # Add timeout to prevent hanging - give extra time for connection setup
        await asyncio.wait_for(websocket_client.connect(), timeout=test_duration + 60)
    except asyncio.TimeoutError:
        print("Test timed out during connection")
    except KeyboardInterrupt:
        print("Test interrupted by user")
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        # Force cleanup with multiple attempts if needed
        cleanup_attempts = 0
        max_cleanup_attempts = 3

        while cleanup_attempts < max_cleanup_attempts:
            try:
                print(f"Cleanup attempt {cleanup_attempts + 1}/{max_cleanup_attempts}")
                await asyncio.wait_for(websocket_client.stop(), timeout=10.0)
                print("Cleanup successful")
                break
            except asyncio.TimeoutError:
                cleanup_attempts += 1
                print(f"Warning: Stop operation timed out (attempt {cleanup_attempts})")
                if cleanup_attempts >= max_cleanup_attempts:
                    print("Force stopping after multiple timeout attempts")
                    websocket_client.running = False
                    break
            except Exception as e:
                cleanup_attempts += 1
                print(f"Error during stop (attempt {cleanup_attempts}): {e}")
                if cleanup_attempts >= max_cleanup_attempts:
                    print("Force stopping after multiple error attempts")
                    websocket_client.running = False
                    break

        print("Test completed")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_bybit_orderbook_websocket_multi(test_duration=60))
