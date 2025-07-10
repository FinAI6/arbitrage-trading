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

        # Todo: asyncio Event를 정의하고 set과 wait, clear를 통해 polling 방식 -> Event Driven 방식으로 변경 -> 뒤에 Monitoring도

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

        # Todo: Orderbook 형태 Data Parsing -> Spread가 2개가 됨 (일단은 아무거나 한개로 진행?)
        # Find overlapping symbols
        binance_symbols = set(binance_data.keys())
        bybit_symbols = set(bybit_data.keys())
        common_symbols = binance_symbols.intersection(bybit_symbols)

        # Calculate spread for each common symbol
        for symbol in common_symbols:
            binance_bid_price = binance_data[symbol][0]
            binance_ask_price = binance_data[symbol][1]
            binance_volume = binance_data[symbol][-1]
            bybit_bid_price = bybit_data[symbol][0]
            bybit_ask_price = bybit_data[symbol][1]
            bybit_volume = bybit_data[symbol][-1]
            # binance_price = binance_data[symbol][0]
            # bybit_price = bybit_data[symbol][0]
            # binance_volume = binance_data[symbol][1]
            # bybit_volume = bybit_data[symbol][1]

            # Skip if either price is zero to avoid division by zero
            if binance_bid_price <= 0 or binance_ask_price <= 0 or bybit_bid_price <= 0 or bybit_ask_price <= 0:
                continue

            # Calculate positive(Binance(short 예정) > Bybit(long 예정)) spread percent
            positive_min_price = min(binance_bid_price, bybit_ask_price)
            positive_spread_pct = (binance_bid_price - bybit_ask_price) / positive_min_price * 100
            if positive_spread_pct >= self.arb_threshold:
                positive_spread_check = True
            else:
                positive_spread_check = False

            # Calculate negative(Binance(long 예정) < Bybit(short 예정)) spread percent
            negative_min_price = min(binance_ask_price, bybit_bid_price)
            negative_spread_pct = (binance_ask_price - bybit_bid_price) / negative_min_price * 100
            if negative_spread_pct <= -self.arb_threshold:
                negative_spread_check = True
            else:
                negative_spread_check = False

            # # Calculate spread percentage
            # min_price = min(binance_price, bybit_price)
            # spread_pct = (binance_price - bybit_price) / min_price * 100
            # if spread_pct >= self.arb_threshold:
            #     positive_spread = True
            #     negative_spread = False
            # elif spread_pct <= -self.arb_threshold:
            #     positive_spread = False
            #     negative_spread = True
            # else:
            #     positive_spread = False
            #     negative_spread = False

            # Initialize deque if this is a new symbol
            if symbol not in self.spread_data:
                self.spread_data[symbol] = deque(maxlen=self.max_deque_length)

            # Add spread data to the deque
            self.spread_data[symbol].append({
                'timestamp': asyncio.get_event_loop().time(),
                'binance_bid_price': binance_bid_price,
                'binance_ask_price': binance_ask_price,
                'bybit_bid_price': bybit_bid_price,
                'bybit_ask_price': bybit_ask_price,
                'binance_volume': binance_volume,
                'bybit_volume': bybit_volume,
                'positive_spread_pct': positive_spread_pct,
                'negative_spread_pct': negative_spread_pct,
                'positive_spread_check': positive_spread_check,
                'negative_spread_check': negative_spread_check,
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
                latest_spreads[symbol] = {"positive_spread": data_deque[-1]['positive_spread_pct'],
                                          "negative_spread": data_deque[-1]['negative_spread_pct'],}
        return latest_spreads

    def get_lastest_spread_by_symbol(self, symbol):
        return self.spread_data[symbol][-1]

    async def stop(self):
        """Stop the aggregation process"""
        self.running = False
