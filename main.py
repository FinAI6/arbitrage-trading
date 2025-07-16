import asyncio
import signal
import sys
import argparse
from datetime import datetime
from exchange.binance_websocket import BinanceWebsocket
from exchange.bybit_websocket import BybitWebsocket
from exchange.binance_orderbook_websocket import BinanceOrderbookWebsocket
from exchange.bybit_orderbook_websocket import BybitOrderbookWebsocket
from aggregation_manager import AggregationManager
from trading_manager import TradingManager
from monitoring_manager import MonitoringManager
from config_manager import ConfigManager
from api_manager import ApiManager


# No need to specify symbols, they will be fetched dynamically from the exchanges
# If you want to use specific symbols, uncomment and modify the following:
# SYMBOLS = [
#     "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
#     "ADAUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "LTCUSDT"
# ]

# Constants are now read from config.ini

async def display_spreads(aggregation_manager, trading_manager, interval):
    """
    Periodically display the latest spread information and system status

    Args:
        aggregation_manager: Instance of AggregationManager
        trading_manager: Instance of TradingManager
        interval (float): Interval in seconds between displays
    """
    while True:
        latest_spreads = aggregation_manager.get_latest_spreads()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if latest_spreads:
            print("\n" + "="*80)
            print(f"📊 ARBITRAGE SYSTEM STATUS - {current_time}")
            print("="*80)

            # System overview
            active_trades = len(trading_manager.tasks)
            max_trades = trading_manager.max_symbols
            total_symbols = len(latest_spreads)

            print(f"🔄 Active Trades: {active_trades}/{max_trades}")
            print(f"📈 Monitored Symbols: {total_symbols}")

            if active_trades > 0:
                print(f"🎯 Trading Symbols: {list(trading_manager.tasks.keys())}")

            print("-" * 80)

            # Sort by absolute spread percentage (descending)
            sorted_spreads = sorted(
                latest_spreads.items(), 
                key=lambda x: abs(x[1]), 
                reverse=True
            )

            # Show top 10 spreads
            print("🔝 TOP SPREADS:")
            for i, (symbol, spread_pct) in enumerate(sorted_spreads[:10]):
                spread_data = aggregation_manager.get_spread_data()[symbol][-1]
                binance_price = spread_data['binance_price']
                bybit_price = spread_data['bybit_price']
                binance_volume = spread_data['binance_volume']
                bybit_volume = spread_data['bybit_volume']

                # Determine direction and color
                direction = "🟢 BUY BINANCE/SELL BYBIT" if spread_pct > 0 else "🔴 SELL BINANCE/BUY BYBIT"
                status = "🎯 TRADING" if symbol in trading_manager.tasks else "👀 MONITORING"

                print(f"{i+1:2d}. {symbol:15s} | {spread_pct:+7.3f}% | {direction} | {status}")
                print(f"     💰 Binance: ${binance_price:>12.6f} (Vol: ${binance_volume:>10,.0f})")
                print(f"     💰 Bybit:   ${bybit_price:>12.6f} (Vol: ${bybit_volume:>10,.0f})")
                print()

            print("="*80)
        else:
            print(f"\n⏳ [{current_time}] Waiting for spread data...")

        await asyncio.sleep(interval)


async def main(test_duration_override=None, display_interval_override=None):

    binance_client = BinanceOrderbookWebsocket()
    bybit_client = BybitOrderbookWebsocket()
    await set_common_symbol(binance_client, bybit_client)

    config_manager = ConfigManager()

    # Use command line arguments if provided, otherwise use config values
    test_duration = test_duration_override if test_duration_override is not None else config_manager.getint('DEFAULT', 'test_duration')
    display_interval = display_interval_override if display_interval_override is not None else config_manager.getint('DEFAULT', 'display_interval')

    # Initialize aggregator
    aggregation_manager = AggregationManager(
        binance_client=binance_client,
        bybit_client=bybit_client
    )

    api_manager = ApiManager()

    # Initialize trading and monitoring managers
    trading_manager = TradingManager(aggregation_manager=aggregation_manager, api_manager=api_manager)
    monitoring_manager = MonitoringManager(aggregation_manager=aggregation_manager, trading_manager=trading_manager)

    # Set up signal handlers for graceful shutdown
    # Using a platform-independent approach for signal handling
    # Windows doesn't support loop.add_signal_handler()
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(
                    binance_client, bybit_client, aggregation_manager, trading_manager, monitoring_manager, api_manager)))
            except NotImplementedError:
                # On Windows, we'll rely on KeyboardInterrupt exception instead
                pass
    except Exception as e:
        print(f"Warning: Could not set up signal handlers: {e}")

    # Start all tasks
    tasks = [
        asyncio.create_task(binance_client.connect()),
        asyncio.create_task(bybit_client.connect()),
        asyncio.create_task(aggregation_manager.start()),
        asyncio.create_task(monitoring_manager.start()),
        asyncio.create_task(api_manager.start()),
        # asyncio.create_task(display_spreads(aggregation_manager, trading_manager, display_interval))
    ]
    # tasks = [
    #     asyncio.create_task(binance_client.connect()),
    # ]

    print("Starting WebSocket connections, aggregation_manager, and managers...")

    if test_duration > 0:
        # Run for a specified duration and then exit
        print(f"Test mode: Will run for {test_duration} seconds")
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=test_duration)
        except asyncio.TimeoutError:
            print(f"\nTest completed after {test_duration} seconds")
            await shutdown(binance_client, bybit_client, aggregation_manager, trading_manager, monitoring_manager)
    else:
        # Run indefinitely until interrupted
        await asyncio.gather(*tasks)

async def shutdown(binance_client, bybit_client, aggregation_manager, trading_manager=None, monitoring_manager=None, api_manager=None, *args, **kwargs):
    """
    Gracefully shut down all components
    """
    print("\nShutting down...")

    # Stop all components
    if monitoring_manager:
        await monitoring_manager.stop()
    # if trading_manager:
    #     await trading_manager.stop()
    await aggregation_manager.stop()
    await binance_client.stop()
    await bybit_client.stop()
    await api_manager.stop()

    # Cancel all tasks except the current one
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    if tasks:
        print(f"Cancelling {len(tasks)} pending tasks...")
        for task in tasks:
            task.cancel()

        # Wait for all tasks to be cancelled
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            print(f"Error during task cancellation: {e}")

    # Don't stop the event loop here, let asyncio.run() handle it
    print("Shutdown complete")

def parse_arguments():
    """Parse command line arguments"""
    config_manager = ConfigManager()
    default_test_duration = config_manager.getint('DEFAULT', 'test_duration')
    default_display_interval = config_manager.getint('DEFAULT', 'display_interval')

    parser = argparse.ArgumentParser(description='Crypto Exchange Arbitrage Monitor')
    parser.add_argument(
        '--test', '-t', 
        type=int, 
        default=default_test_duration,
        help=f'Run in test mode for specified number of seconds (default: {default_test_duration}, 0 for indefinite)'
    )
    parser.add_argument(
        '--display-interval', '-d',
        type=float,
        default=default_display_interval,
        help=f'Interval in seconds between spread displays (default: {default_display_interval})'
    )
    return parser.parse_args()


async def set_common_symbol(binance_client, bybit_client):
    binance_symbols, bybit_symbols = await asyncio.gather(
        binance_client.fetch_all_symbols(),
        bybit_client.fetch_all_symbols()
    )
    binance_symbols_set = set([x.upper() for x in binance_symbols])
    bybit_symbols_set = set(bybit_symbols)

    common_symbols_set = binance_symbols_set.intersection(bybit_symbols_set)
    common_symbols = list(common_symbols_set)

    binance_client.set_symbols([x.lower() for x in common_symbols])
    bybit_client.set_symbols(common_symbols)
    print(f"Common symbols are set to {common_symbols}.")


if __name__ == "__main__":
    # Windows 환경인지 확인
    if sys.platform == 'win32':
        # SelectorEventLoop로 강제로 설정
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        args = parse_arguments()

        # Command line arguments are now handled directly in main() function
        # No need to override global constants since they're read from config

        # On Windows, use SelectorEventLoop instead of ProactorEventLoop
        # This is needed for aiodns to work properly
        if sys.platform.startswith('win'):
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            print("Using WindowsSelectorEventLoopPolicy for Windows compatibility")

        asyncio.run(main(args.test, args.display_interval))
    except KeyboardInterrupt:
        print("Program terminated by user")
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print("Traceback:")
        traceback.print_exc()
    finally:
        print("Program exited")
