import asyncio
import json
import time
import logging
from datetime import datetime
from aggregation_manager import AggregationManager
from exchange.binance_orderbook_websocket import BinanceOrderbookWebsocket
from exchange.bybit_orderbook_websocket import BybitOrderbookWebsocket

# Configure logging for CSV format
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Remove timestamp formatting for CSV
    handlers=[
        logging.FileHandler('orderbook_websocket_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# CSV header flag to ensure it's written only once
csv_header_written = False

class BinanceOrderbookWebsocketWithTimestamp(BinanceOrderbookWebsocket):
    """Extended Binance websocket class that captures timestamps"""

    def __init__(self, symbols=None, test_duration=None):
        super().__init__(symbols, test_duration)
        self.timestamps = {}  # Store timestamps for each symbol

    async def handle_message(self, message):
        """
        Process incoming WebSocket messages with timestamp parsing
        Uses original structure and only adds timestamp capture
        """
        # First call the parent's handle_message to preserve all original functionality
        await super().handle_message(message)

        # Then add timestamp capture functionality
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Handle bookTicker data format for futures - only capture timestamp
        if 's' in data and 'b' in data and 'a' in data:
            symbol = data['s'].upper()
            # Extract timestamp if available (E field is event time in milliseconds)
            ws_timestamp = data.get('E', int(time.time() * 1000))
            self.timestamps[symbol] = ws_timestamp

    def get_data_with_timestamp(self):
        """Get data with timestamps"""
        return self.data, self.timestamps

class BybitOrderbookWebsocketWithTimestamp(BybitOrderbookWebsocket):
    """Extended Bybit websocket class that captures timestamps"""

    def __init__(self, symbols=None, test_duration=None):
        super().__init__(symbols, test_duration)
        self.timestamps = {}  # Store timestamps for each symbol

    async def handle_message(self, message):
        """
        Process incoming WebSocket messages with timestamp parsing
        Uses original structure and only adds timestamp capture
        """
        # First call the parent's handle_message to preserve all original functionality
        await super().handle_message(message)

        # Then add timestamp capture functionality
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Handle orderbook.1 data - only capture timestamp
        if 'topic' in data and 'data' in data:
            if data['topic'].startswith('orderbook.1.'):
                topic_parts = data['topic'].split('.')
                if len(topic_parts) >= 3:
                    symbol = topic_parts[2]
                    # Extract timestamp (ts field is common in Bybit websockets)
                    ws_timestamp = data.get('ts', int(time.time() * 1000))
                    self.timestamps[symbol] = ws_timestamp

    def get_data_with_timestamp(self):
        """Get data with timestamps"""
        return self.data, self.timestamps

class AggregationManagerWithLogging(AggregationManager):
    """Extended AggregationManager that logs orderbook data"""

    def __init__(self, binance_client, bybit_client):
        super().__init__(binance_client, bybit_client)
        self.target_symbols = ["MAGICUSDT", "PORTALUSDT", "HYPERUSDT"]

    async def aggregate_data_with_logging(self):
        """
        Aggregate data and log the specified symbols with timestamps in CSV format
        """
        global csv_header_written

        # Write CSV header only once
        if not csv_header_written:
            header = "current_time,symbol,binance_timestamp,binance_bid_price,binance_ask_price,bybit_timestamp,bybit_bid_price,bybit_ask_price"
            logger.info(header)
            csv_header_written = True

        # Get data from both clients
        binance_data, binance_timestamps = self.binance_client.get_data_with_timestamp()
        bybit_data, bybit_timestamps = self.bybit_client.get_data_with_timestamp()

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Log data for target symbols in CSV format
        for symbol in self.target_symbols:
            # Initialize default values
            binance_bid = "N/A"
            binance_ask = "N/A"
            binance_ts = "N/A"
            bybit_bid = "N/A"
            bybit_ask = "N/A"
            bybit_ts = "N/A"

            # Extract Binance data
            if symbol in binance_data:
                bid_price, ask_price = binance_data[symbol][:2]
                binance_bid = f"{bid_price:.6f}"
                binance_ask = f"{ask_price:.6f}"
                binance_ts_raw = binance_timestamps.get(symbol, "N/A")
                if binance_ts_raw != "N/A":
                    binance_ts = datetime.fromtimestamp(binance_ts_raw/1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # Extract Bybit data
            if symbol in bybit_data:
                bid_price, ask_price = bybit_data[symbol][:2]
                bybit_bid = f"{bid_price:.6f}"
                bybit_ask = f"{ask_price:.6f}"
                bybit_ts_raw = bybit_timestamps.get(symbol, "N/A")
                if bybit_ts_raw != "N/A":
                    bybit_ts = datetime.fromtimestamp(bybit_ts_raw/1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # Create CSV row
            csv_row = f"{current_time},{symbol},{binance_ts},{binance_bid},{binance_ask},{bybit_ts},{bybit_bid},{bybit_ask}"
            logger.info(csv_row)

async def test_orderbook_websocket_logging(test_duration=60):
    """
    Test Binance and Bybit Orderbook WebSocket with logging

    Args:
        test_duration (int): Test duration in seconds
    """
    print(f"Starting Orderbook WebSocket logging test for {test_duration} seconds...")

    # Target symbols
    target_symbols = ["MAGICUSDT", "PORTALUSDT", "HYPERUSDT"]

    # Initialize websocket clients with timestamp support
    binance_client = BinanceOrderbookWebsocketWithTimestamp(
        # symbols=[s.lower() for s in target_symbols],
        test_duration=test_duration
    )
    bybit_client = BybitOrderbookWebsocketWithTimestamp(
        # symbols=target_symbols,
        test_duration=test_duration
    )

    # Initialize aggregation manager
    aggregation_manager = AggregationManagerWithLogging(binance_client, bybit_client)

    try:
        # Start websocket connections
        print("Connecting to Binance and Bybit websockets...")
        binance_task = asyncio.create_task(binance_client.connect())
        bybit_task = asyncio.create_task(bybit_client.connect())

        # Wait a bit for connections to establish
        await asyncio.sleep(3)

        # Start logging loop
        start_time = time.time()
        log_interval = 10  # Log every 10 seconds

        while time.time() - start_time < test_duration:
            await aggregation_manager.aggregate_data_with_logging()
            await asyncio.sleep(log_interval)

        print(f"\nTest completed after {test_duration} seconds")

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        # Stop websocket connections
        await binance_client.stop()
        await bybit_client.stop()

        # Cancel tasks if they're still running
        if not binance_task.done():
            binance_task.cancel()
        if not bybit_task.done():
            bybit_task.cancel()

if __name__ == "__main__":
    import sys

    # Set event loop policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Run test for 60 seconds (can be changed)
    test_duration = 36000
    if len(sys.argv) > 1:
        try:
            test_duration = int(sys.argv[1])
        except ValueError:
            print("Invalid duration provided, using default 60 seconds")

    asyncio.run(test_orderbook_websocket_logging(test_duration))
