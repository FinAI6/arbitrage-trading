import asyncio
import json
import websockets
import aiohttp
import sys
from collections import deque
from datetime import datetime


class BinanceOrderbookWebsocket:
    def __init__(self, symbols=None, test_duration=None):
        """
        Initialize Binance Orderbook WebSocket client
        
        Args:
            symbols (list): List of symbols to subscribe to. If None, fetches all available symbols
            test_duration (int): Test duration in seconds. If provided, connection will auto-stop after this time
        """
        self.symbols = symbols or []
        self.test_duration = test_duration
        self.ws_url = "wss://fstream.binance.com/stream?streams="
        self.data = {}  # Dictionary to store symbol:(bid_price, ask_price, bid_qty, ask_qty) data
        self.running = False
        self.start_time = None

    async def fetch_all_symbols(self):
        """
        Fetch all available USDT futures trading pairs from Binance
        
        Returns:
            list: List of symbol names
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://fapi.binance.com/fapi/v1/exchangeInfo') as response:
                    if response.status == 200:
                        data = await response.json()
                        symbols = [
                            symbol['symbol'].lower() 
                            for symbol in data['symbols'] 
                            if symbol['status'] == 'TRADING' and symbol['symbol'].endswith('USDT')
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
        """Connect to Binance WebSocket and subscribe to bookTicker streams"""
        # Record start time for test duration
        self.start_time = datetime.now()
        
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
        max_streams_per_connection = 100
        symbol_chunks = [self.symbols[i:i + max_streams_per_connection] 
                         for i in range(0, len(self.symbols), max_streams_per_connection)]

        # Create a task for each chunk
        tasks = []
        for chunk in symbol_chunks:
            tasks.append(asyncio.create_task(self._connect_to_streams(chunk)))

        # Add test duration monitoring task if specified
        if self.test_duration:
            tasks.append(asyncio.create_task(self._monitor_test_duration()))

        # Wait for all connections to complete
        try:
            # Using gather with return_exceptions=True to prevent one failed task from causing all to fail
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if all tasks failed
            all_failed = all(isinstance(result, Exception) for result in results)
            if all_failed:
                print("All Binance OrderBook WebSocket connections failed. Check network connectivity.")

            # Log any exceptions that occurred
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Binance OrderBook WebSocket connection {i+1} failed with error: {result}")

        except Exception as e:
            print(f"Error managing Binance OrderBook WebSocket connections: {e}")

        finally:
            # If we get here and running is still True, connections are being maintained
            # by the reconnection logic in _connect_to_streams
            pass

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

    async def _connect_to_streams(self, symbols):
        """
        Connect to WebSocket streams for a subset of symbols
        
        Args:
            symbols (list): List of symbols to subscribe to
        """
        # For order book data, we use bookTicker streams which provide best bid/ask prices
        streams = [f"{symbol}@bookTicker" for symbol in symbols]
        connection_url = f"{self.ws_url}{'/'.join(streams)}"

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
                    connection_url,
                    ping_interval=None,  # < 3분 서버 ping주기보다 짧거나 비슷하게
                    ping_timeout=None,  # 네트워크 지연 감지용
                    max_queue=None,  # 백프레셔 방지(옵션)
                    close_timeout=5,
                ) as websocket:
                    print(f"Connected to Binance OrderBook WebSocket for {len(symbols)} symbols")

                    # Reset retry count on successful connection
                    retry_count = 0

                    while self.running:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=10)
                            await self.handle_message(message)
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"Binance OrderBook WebSocket connection closed: {e}")
                            break
                        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                            # Network connection error handling
                            print(f"Binance OrderBook WebSocket network error: {e}")
                            break
                        except Exception as e:
                            print(f"Error in Binance OrderBook WebSocket message handling: {e}")
                            # Continue processing other messages if there's an error with one
                            continue

            except websockets.exceptions.ConnectionClosed:
                if not self.running:
                    # If we're intentionally stopping, don't try to reconnect
                    print("Binance OrderBook WebSocket connection closed by user")
                    break
                print("Binance OrderBook WebSocket connection closed, attempting to reconnect...")
                
            except websockets.exceptions.WebSocketException as e:
                print(f"Binance OrderBook WebSocket exception: {e}")
                if not self.running:
                    break
                    
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                print(f"Binance OrderBook WebSocket network error: {e}")
                if not self.running:
                    break

            except Exception as e:
                print(f"Unexpected error in Binance OrderBook WebSocket connection: {e}")
                if not self.running:
                    break

            # Reconnection logic
            if not self.running:
                break
                
            retry_count += 1
            if retry_count > max_retries:
                print(f"Binance OrderBook WebSocket failed to reconnect after {max_retries} attempts. Giving up.")
                break

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"Binance OrderBook WebSocket reconnecting in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
            await asyncio.sleep(delay)

        print(f"Binance OrderBook WebSocket connection permanently closed for {len(symbols)} symbols")

    async def handle_message(self, message):
        """
        Process incoming WebSocket messages
        
        Args:
            message (str): JSON message from WebSocket
        """
        try:
            data = json.loads(message)['data']
        except json.JSONDecodeError:
            print(f"Invalid JSON received: {message}")
            return

        # Handle bookTicker data format for futures
        # bookTicker format: {"u":400900217,"s":"BNBUSDT","b":"25.35000000","B":"31.21000000","a":"25.36000000","A":"40.66000000"}
        # u: order book updateId, s: symbol, b: best bid price, B: best bid qty, a: best ask price, A: best ask qty
        if 's' in data and 'b' in data and 'a' in data:
            symbol = data['s'].upper()  # Symbol is uppercase in Binance response
            bid_price = float(data['b'])    # Best bid price
            ask_price = float(data['a'])    # Best ask price
            bid_qty = float(data['B'])      # Best bid quantity
            ask_qty = float(data['A'])      # Best ask quantity

            ws_timestamp = data.get('E')

            # Store as (bid_price, ask_price, bid_qty, ask_qty)
            # Binance 24h Volume = 0
            # self.data[symbol] = (bid_price, ask_price, bid_qty, ask_qty, 0)
            self.data[symbol] = (bid_price, ask_price, bid_qty, ask_qty, 0, ws_timestamp)
            
            # Optional: Print sample data for debugging
            # if symbol == "CHILLGUYUSDT":
            #     print(f"ORDERBOOK: {datetime.now()} {symbol} Bid: {bid_price} Ask: {ask_price}")

    def get_data(self):
        """
        Get current orderbook data for all subscribed symbols
        
        Returns:
            dict: Dictionary of symbol:(bid_price, ask_price, bid_qty, ask_qty) tuples
        """
        return self.data

    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    async def stop(self):
        """Stop the WebSocket connection"""
        self.running = False
        print("Binance OrderBook WebSocket stopping...")


# Test function
async def test_binance_orderbook_websocket(test_duration=30):
    """
    Test Binance OrderBook WebSocket connection
    
    Args:
        test_duration (int): Test duration in seconds
    """
    print(f"Starting Binance OrderBook WebSocket test for {test_duration} seconds...")
    
    # Test with a few popular symbols
    test_symbols = ['btcusdt', 'ethusdt', 'adausdt', 'dotusdt', 'linkusdt']
    
    websocket_client = BinanceOrderbookWebsocket(symbols=test_symbols, test_duration=test_duration)
    
    try:
        await websocket_client.connect()
        
        # Print final data summary
        data = websocket_client.get_data()
        print(f"\nTest completed. Received data for {len(data)} symbols:")
        for symbol, (bid_price, ask_price, bid_qty, ask_qty) in list(data.items())[:10]:  # Show first 10
            spread = ask_price - bid_price
            spread_pct = (spread / bid_price) * 100 if bid_price > 0 else 0
            print(f"{symbol}: Bid={bid_price:.6f} Ask={ask_price:.6f} Spread={spread:.6f} ({spread_pct:.4f}%)")
            
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
    asyncio.run(test_binance_orderbook_websocket())