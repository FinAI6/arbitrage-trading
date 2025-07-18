import asyncio
import json
from datetime import datetime
import aiofiles

from aggregation_manager import AggregationManager
from trading_manager import TradingManager
from config_manager import ConfigManager
from logging_manager import get_monitoring_logger

class MonitoringManager:
    def __init__(self, aggregation_manager: AggregationManager, trading_manager: TradingManager):
        """
        Initialize the Monitoring Manager

        Args:
            aggregator: Instance of ExchangeAggregator to get market data
            trading_manager: Instance of TradingManager to send selected symbols to
        """
        self.aggregation_manager = aggregation_manager
        self.trading_manager = trading_manager
        self.config_manager = ConfigManager()
        self.logger = get_monitoring_logger()

        # Read parameters from config.ini
        self.consecutive_count = self.config_manager.getint('MONITORING', 'consecutive_count')
        self.top_symbols = self.config_manager.getint('MONITORING', 'top_symbols')
        self.minimum_usdt_volume = self.config_manager.getint('MONITORING', 'minimum_usdt_volume')
        self.top_volume_num = self.config_manager.getint('MONITORING', 'top_volume_num')
        self.running = False

        self.last_timestamp_too_old_print_time = datetime.now()

    async def start(self, interval: float = None):
        """
        Start the Monitoring Manager

        Args:
            interval: Interval in seconds between monitoring checks (optional, uses config if not provided)
        """
        if interval is None:
            interval = self.config_manager.getfloat('MONITORING', 'interval')

        self.running = True

        count = 0
        while self.running:
            count += 1
            await self.monitor_spreads()
            if count % 60000 == 1:
                latest_data = self.aggregation_manager.get_latest_spreads()
                async with aiofiles.open('spread_log.txt', 'a+') as f:
                    await f.write(f"[{datetime.now()}]\n{json.dumps(latest_data, ensure_ascii=False)}\n\n")
            await asyncio.sleep(interval)

    async def monitor_spreads(self):
        """
        Monitor spread data and identify symbols with consecutive positive/negative spreads
        """
        # Get all spread data from the aggregator
        # await asyncio.sleep(15)

        spread_data = self.aggregation_manager.get_spread_data()

        # Filter out symbols with less than 24h USDT volume
        spread_data = {key: value for key, value in spread_data.items() if value[-1]['bybit_volume'] >= self.minimum_usdt_volume}

        spread_symbol_list_by_volume = sorted(
            spread_data,
            key=lambda x: spread_data[x][-1]['bybit_volume'],
            reverse=True
        )
        top_volume_symbol_list = spread_symbol_list_by_volume[:self.top_volume_num]

        spread_data = {x: spread_data[x] for x in top_volume_symbol_list}

        # Lists to store symbols with consecutive positive/negative spreads
        positive_consecutive: list[tuple[str, dict]] = []
        negative_consecutive: list[tuple[str, dict]] = []

        # Check each symbol for consecutive positive/negative spreads
        for symbol, data_deque in spread_data.items():
            if len(data_deque) < self.consecutive_count:
                continue

            # if list(data_deque)[-1]['spread_pct'] >= 0.2:
            #     print(datetime.now(), symbol, list(data_deque)[-1]['spread_pct'])

            # Check last n entries for consecutive positive spreads
            if all(entry['positive_spread_check'] for entry in list(data_deque)[-self.consecutive_count:]):
                # Calculate average spread percentage for ranking
                avg_spread_pct = sum(abs(entry['positive_spread_pct']) for entry in list(data_deque)[-self.consecutive_count:]) / self.consecutive_count
                positive_consecutive.append((symbol, {
                    'spread_pct': avg_spread_pct,
                    'direction': 'positive',
                    'data': list(data_deque)[-self.consecutive_count:]
                }))

            # Check last n entries for consecutive negative spreads
            elif all(entry['negative_spread_check'] for entry in list(data_deque)[-self.consecutive_count:]):
                # Calculate average spread percentage for ranking
                avg_spread_pct = sum(abs(entry['negative_spread_pct']) for entry in list(data_deque)[-self.consecutive_count:]) / self.consecutive_count
                negative_consecutive.append((symbol, {
                    'spread_pct': avg_spread_pct,
                    'direction': 'negative',
                    'data': list(data_deque)[-self.consecutive_count:]
                }))

        # Combine and sort by absolute spread percentage (descending)
        all_consecutive: list[tuple[str, dict]] = positive_consecutive + negative_consecutive

        sorted_consecutive: list[tuple[str, dict]] = sorted(
            all_consecutive,
            key=lambda x: x[1]['spread_pct'],
            reverse=True
        )

        # Select top symbols
        top_symbols: list[tuple[str, dict]] = sorted_consecutive[:self.top_symbols]

        # Send to Trading Manager if we have any symbols
        if top_symbols:
            for i, (symbol, data) in enumerate(top_symbols):

                # Websocket Data가 Update 안되는 상황 확인
                time_diff_threshold = 10

                current_datetime = datetime.now()
                binance_datetime = datetime.fromtimestamp(data['data'][-1]['binance_timestamp'] / 1000)
                bybit_datetime = datetime.fromtimestamp(data['data'][-1]['bybit_timestamp'] / 1000)

                if abs((current_datetime - binance_datetime).total_seconds()) > time_diff_threshold or abs((current_datetime - bybit_datetime).total_seconds()) > time_diff_threshold:
                    if (current_datetime - self.last_timestamp_too_old_print_time).total_seconds() > 60:
                        self.logger.warning(f"Timestamp too old - Current: {current_datetime}, Binance: {binance_datetime}, Bybit: {bybit_datetime}")
                        self.last_timestamp_too_old_print_time = current_datetime
                    continue

                if symbol in self.trading_manager.black_list:
                    continue

                success = await self.trading_manager.add_symbol(symbol, data['direction'] == 'positive')
                if success:
                    self.logger.info(f"\n🔍 [Monitoring Manager] Found {len(top_symbols)} trading opportunities:")
                    direction_str = "🟢 LONG BINANCE/SHORT BYBIT" if data['direction'] == 'positive' else "🔴 SHORT BINANCE/LONG BYBIT"
                    self.logger.info(f"   {i + 1}. {symbol}: {data['spread_pct']:.3f}% avg spread | {direction_str}")
                    # self.logger.debug(f"      ❌ Failed to add {symbol} to trading")
        else:
            # Only print this occasionally to avoid spam
            import time
            if not hasattr(self, '_last_no_opportunities_print'):
                self._last_no_opportunities_print = 0

            current_time = time.time()
            if current_time - self._last_no_opportunities_print > 300:  # Log every 5 minutes
                self.logger.info(f"🔍 [Monitoring Manager] No trading opportunities found (spread threshold: {self.config_manager.getfloat('AGGREGATION', 'arb_threshold'):.3f}%)")
                self._last_no_opportunities_print = current_time

    def get_consecutive_count(self):
        """
        Get the current consecutive count setting

        Returns:
            int: The number of consecutive positive/negative spreads required
        """
        return self.consecutive_count

    def set_consecutive_count(self, count: int):
        """
        Set the consecutive count setting

        Args:
            count: Number of consecutive positive/negative spreads required
        """
        if count > 0:
            self.consecutive_count = count

    def get_top_symbols_count(self):
        """
        Get the current top symbols count setting

        Returns:
            int: The number of top symbols to select
        """
        return self.top_symbols

    def set_top_symbols_count(self, count: int):
        """
        Set the top symbols count setting

        Args:
            count: Number of top symbols to select
        """
        if count > 0:
            self.top_symbols = count

    async def stop(self):
        """Stop the Monitoring Manager"""
        self.running = False
