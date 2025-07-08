import asyncio
import json
import websockets
import aiohttp
from collections import deque
from datetime import datetime


class BinanceWebsocket:
    def __init__(self, symbols=None):
        """
        Initialize Binance WebSocket client

        Args:
            symbols (list, optional): List of symbols to subscribe to. If None, all available symbols will be fetched.
        """
        self.symbols = []
        if symbols:
            self.symbols = [symbol.lower() for symbol in symbols]
        self.ws_url = "wss://fstream.binance.com/ws"  # Futures WebSocket URL
        self.rest_api_url = "https://fapi.binance.com"  # Futures REST API URL
        self.data = {}
        self.running = False

    async def fetch_all_symbols(self):
        """
        Fetch all available USDT futures trading pairs from Binance

        Returns:
            list: List of all available USDT futures symbols
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_api_url}/fapi/v1/exchangeInfo") as response:
                    if response.status == 200:
                        data = await response.json()
                        # Filter for USDT futures trading pairs that are currently trading
                        symbols = [
                            symbol["symbol"].lower() 
                            for symbol in data["symbols"] 
                            if symbol["symbol"].endswith("USDT") and symbol["status"] == "TRADING" and symbol["contractType"] == "PERPETUAL"
                        ]
                        print(f"Fetched {len(symbols)} USDT futures trading pairs from Binance")
                        return symbols
                    else:
                        print(f"Error fetching Binance futures symbols: HTTP {response.status}")
                        return []
        except Exception as e:
            print(f"Error fetching Binance futures symbols: {e}")
            return []

    async def connect(self):
        """Connect to Binance WebSocket and subscribe to ticker streams"""
        # If no symbols were provided, fetch all available symbols
        if not self.symbols:
            self.symbols = await self.fetch_all_symbols()

        if not self.symbols:
            print("No symbols available for Binance. Cannot connect to WebSocket.")
            return

        # Set running to True at the beginning
        self.running = True

        # Binance has a limit on the number of streams per connection
        # Split into chunks of 200 symbols if needed
        max_streams_per_connection = 200
        symbol_chunks = [self.symbols[i:i + max_streams_per_connection] 
                         for i in range(0, len(self.symbols), max_streams_per_connection)]

        # Create a task for each chunk
        tasks = []
        for chunk in symbol_chunks:
            tasks.append(asyncio.create_task(self._connect_to_streams(chunk)))

        # Wait for all connections to complete
        try:
            # Using gather with return_exceptions=True to prevent one failed task from causing all to fail
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if all tasks failed
            all_failed = all(isinstance(result, Exception) for result in results)
            if all_failed:
                print("All Binance WebSocket connections failed. Check network connectivity.")

            # Log any exceptions that occurred
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Binance WebSocket connection {i+1} failed with error: {result}")

        except Exception as e:
            print(f"Error managing Binance WebSocket connections: {e}")

        finally:
            # If we get here and running is still True, connections are being maintained
            # by the reconnection logic in _connect_to_streams
            pass

    async def _connect_to_streams(self, symbols):
        """
        Connect to WebSocket streams for a subset of symbols

        Args:
            symbols (list): List of symbols to subscribe to
        """
        # For futures, we use aggTrade or ticker streams
        streams = [f"{symbol}@aggTrade" for symbol in symbols]
        connection_url = f"{self.ws_url}/{'/'.join(streams)}"

        # Initialize reconnection parameters
        max_retries = 10
        retry_count = 0
        base_delay = 1  # Start with 1 second delay
        max_delay = 60  # Maximum delay of 60 seconds

        while self.running or retry_count == 0:
            try:
                # Set running to True at the beginning of connection attempt
                self.running = True

                # WebSocket 연결에 타임아웃 설정 추가
                async with websockets.connect(
                    connection_url,
                    ping_interval=20,  # 20초마다 ping
                    ping_timeout=10,   # ping 응답 대기 시간
                    close_timeout=10   # 연결 종료 대기 시간
                ) as websocket:
                    print(f"Connected to Binance Futures WebSocket for {len(symbols)} symbols")

                    # Reset retry count on successful connection
                    retry_count = 0

                    while self.running:
                        try:
                            message = await websocket.recv()
                            await self.handle_message(message)
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"Binance Futures WebSocket connection closed: {e}")
                            break
                        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                            # 네트워크 연결 오류 처리
                            print(f"Binance Futures WebSocket network error: {e}")
                            break
                        except Exception as e:
                            print(f"Error in Binance Futures WebSocket message handling: {e}")
                            # Continue processing other messages if there's an error with one
                            continue

            except websockets.exceptions.ConnectionClosed:
                if not self.running:
                    # If we're intentionally stopping, don't try to reconnect
                    print("Binance Futures WebSocket connection closed by user")
                    break
                print("Binance Futures WebSocket connection closed, attempting to reconnect...")
                
            except websockets.exceptions.WebSocketException as e:
                print(f"Binance Futures WebSocket exception: {e}")
                if not self.running:
                    break
                    
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                print(f"Binance Futures WebSocket network error: {e}")
                if not self.running:
                    break

            except Exception as e:
                print(f"Unexpected error in Binance Futures WebSocket connection: {e}")
                if not self.running:
                    break

            # 재연결 로직
            if not self.running:
                break
                
            retry_count += 1
            if retry_count > max_retries:
                print(f"Binance Futures WebSocket failed to reconnect after {max_retries} attempts. Giving up.")
                break

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"Binance Futures WebSocket reconnecting in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
            await asyncio.sleep(delay)

        print(f"Binance Futures WebSocket connection permanently closed for {len(symbols)} symbols")

    async def handle_message(self, message):
        """
        Process incoming WebSocket messages

        Args:
            message (str): JSON message from WebSocket
        """
        data = json.loads(message)
        # Handle aggTrade data format for futures
        if 's' in data and 'p' in data:
            symbol = data['s'].upper()  # Symbol is uppercase in Binance response
            price = float(data['p'])    # 'p' is the price in aggTrade data
            # if symbol == "HFTUSDT" or symbol == "HFT/USDT:USDT":
            #     print(datetime.now(), symbol, price)
            self.data[symbol] = (price, 0)

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