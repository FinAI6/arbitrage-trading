import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Any
from config_manager import ConfigManager


class AggregationManager:
    def __init__(self, binance_client, bybit_client):
        """
        Initialize the aggregator to process data from Binance and Bybit

        Args:
            binance_client: Instance of BinanceWebsocket
            bybit_client: Instance of BybitWebsocket
        """
        self.binance_client = binance_client
        self.bybit_client = bybit_client
        self.config_manager = ConfigManager()

        # Read parameters from config.ini
        self.max_deque_length = self.config_manager.getint('AGGREGATION', 'max_deque_length')
        self.arb_threshold = self.config_manager.getfloat('AGGREGATION', 'arb_threshold')
        self.spread_data: dict[str, deque[dict[str, Any]]] = {}  # Dictionary to store deques of spread data for each symbol
        self.running = False

    async def start(self, interval=None):
        """
        Start the aggregation process

        Args:
            interval (float): Interval in seconds between aggregation updates (optional, uses config if not provided)
        """
        if interval is None:
            interval = self.config_manager.getfloat('AGGREGATION', 'interval')

        self.running = True

        while self.running:
            await self.aggregate_data()
            await asyncio.sleep(interval)

    async def aggregate_data(self):
        """
        Compare prices from both exchanges and calculate spread percentages
        for overlapping symbols
        """
        binance_data = self.binance_client.get_data()
        bybit_data = self.bybit_client.get_data()

        # Find overlapping symbols
        binance_symbols = set(binance_data.keys())
        bybit_symbols = set(bybit_data.keys())
        common_symbols = binance_symbols.intersection(bybit_symbols)

        # Calculate spread for each common symbol
        for symbol in common_symbols:
            binance_price = binance_data[symbol][0]
            bybit_price = bybit_data[symbol][0]
            binance_volume = binance_data[symbol][1]
            bybit_volume = bybit_data[symbol][1]

            # Skip if either price is zero to avoid division by zero
            if binance_price <= 0 or bybit_price <= 0:
                continue

            # Calculate spread percentage
            min_price = min(binance_price, bybit_price)
            spread_pct = (binance_price - bybit_price) / min_price * 100
            if spread_pct >= self.arb_threshold:
                positive_spread = True
                negative_spread = False
            elif spread_pct <= -self.arb_threshold:
                positive_spread = False
                negative_spread = True
            else:
                positive_spread = False
                negative_spread = False

            # Initialize deque if this is a new symbol
            if symbol not in self.spread_data:
                self.spread_data[symbol] = deque(maxlen=self.max_deque_length)

            # Add spread data to the deque
            self.spread_data[symbol].append({
                'timestamp': asyncio.get_event_loop().time(),
                'binance_price': binance_price,
                'bybit_price': bybit_price,
                'binance_volume': binance_volume,
                'bybit_volume': bybit_volume,
                'spread_pct': spread_pct,
                'positive_spread': positive_spread,
                'negative_spread': negative_spread,
            })

    def get_spread_data(self):
        """
        Get the current spread data for all symbols

        Returns:
            dict: Dictionary of symbol:deque pairs containing spread data
        """
        return self.spread_data

    def get_latest_spreads(self):
        """
        Get the latest spread percentage for each symbol

        Returns:
            dict: Dictionary of symbol:latest_spread_pct pairs
        """
        latest_spreads = {}
        for symbol, data_deque in self.spread_data.items():
            if data_deque:  # Check if deque is not empty
                latest_spreads[symbol] = data_deque[-1]['spread_pct']
        return latest_spreads

    def get_lastest_spread_by_symbol(self, symbol):
        return self.spread_data[symbol][-1]

    async def stop(self):
        """Stop the aggregation process"""
        self.running = False
