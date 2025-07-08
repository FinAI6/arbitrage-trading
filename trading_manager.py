import asyncio
from datetime import datetime
import aiofiles
from aggregation_manager import AggregationManager
from trader.taker_taker_trader import TakerTakerTrader
from config_manager import ConfigManager

class TradingManager:
    def __init__(self, aggregation_manager: AggregationManager):
        """
        Initialize the Trading Manager

        Args:
            aggregator: Instance of ExchangeAggregator to get market data
        """
        self.aggregation_manager = aggregation_manager
        self.config_manager = ConfigManager()

        # Read parameters from config.ini
        self.max_symbols = self.config_manager.getint('TRADING', 'max_symbols')
        self.tasks: dict[str, asyncio.Task] = {}
        # self.tracked_symbols = {}  # Dictionary to store symbols being tracked for trading
        # self.running = False

    def full(self) -> bool:  # 자리 확인
        return len(self.tasks) >= self.max_symbols

    async def add_symbol(self, symbol: str, direction: bool) -> bool:
        if self.full() or symbol in self.tasks:  # 꽉차면 거절
            return False

        async with aiofiles.open('./result.txt', mode='a+') as f:
            await f.write(f"[Append Trader][{symbol}][{datetime.now()}]")

        trader = TakerTakerTrader(symbol=symbol, direction=direction, aggregation_manager=self.aggregation_manager)
        task = asyncio.create_task(trader.run(), name=symbol)
        self.tasks[symbol] = task

        direction_str = "🟢 LONG BINANCE/SHORT BYBIT" if direction else "🔴 SHORT BINANCE/LONG BYBIT"
        print(f"🎯 [Trading Manager] Started trading {symbol} | Direction: {direction_str}")
        print(f"📊 [Trading Manager] Active trades: {len(self.tasks)}/{self.max_symbols} | Symbols: {list(self.tasks.keys())}")

        def on_task_done(task):
            self.tasks.pop(symbol, None)
            print(f"✅ [Trading Manager] Completed trading {symbol} | Active trades: {len(self.tasks)}/{self.max_symbols}")
            if len(self.tasks) > 0:
                print(f"📊 [Trading Manager] Remaining symbols: {list(self.tasks.keys())}")

        task.add_done_callback(on_task_done)

        return True

    # async def start(self, interval: float = 1.0):
    #     """
    #     Start the Trading Manager
    #
    #     Args:
    #         interval: Interval in seconds between trading checks
    #     """
    #     self.running = True
    #
    #     while self.running:
    #         # Trading logic will be implemented here in the future
    #         print(f"[Trading Manager] Lists of tracked symbols")
    #         for key, value in self.tracked_symbols.items():
    #             print(f"[Trading Manager] {key}: {value['spread_pct']}")
    #         await asyncio.sleep(interval)
    #
    # def get_latest_spread_data(self, symbol: str = None):
    #     """
    #     Get the latest spread data from the aggregator
    #
    #     Args:
    #         symbol: Optional symbol to get data for. If None, returns data for all symbols
    #
    #     Returns:
    #         The latest spread data for the requested symbol(s)
    #     """
    #     if symbol:
    #         spread_data = self.aggregator.get_spread_data()
    #         return spread_data.get(symbol, [])[-1] if symbol in spread_data and spread_data[symbol] else None
    #     else:
    #         return self.aggregator.get_latest_spreads()
    #
    # def receive_symbol_data(self, symbol_data_list: list[tuple[str, dict]]):
    #     """
    #     Receive symbol data from the Monitoring Manager
    #
    #     Args:
    #         symbol_data_list: List of dictionaries containing symbol data
    #
    #     Returns:
    #         bool: True if data was accepted, False if rejected due to capacity
    #     """
    #     # Check if we have capacity for new symbols
    #     if len(self.tracked_symbols) >= self.max_symbols and any(symbol not in self.tracked_symbols for symbol, _ in symbol_data_list):
    #         return False
    #
    #     # Update tracked symbols with new data
    #     for symbol, data in symbol_data_list:
    #         self.tracked_symbols[symbol] = data
    #
    #     return True
    #
    # def get_tracked_symbols(self):
    #     """
    #     Get the currently tracked symbols
    #
    #     Returns:
    #         dict: Dictionary of tracked symbols and their data
    #     """
    #     return self.tracked_symbols
    #
    # async def stop(self):
    #     """Stop the Trading Manager"""
    #     self.running = False
