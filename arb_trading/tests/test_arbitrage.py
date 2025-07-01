# arb_trading/tests/test_arbitrage.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from arb_trading.core.arbitrage_engine import ArbitrageEngine
from arb_trading.core.spread_monitor import SpreadMonitor, SpreadData
from arb_trading.core.position_manager import PositionManager, ArbitragePosition, PositionStatus
from arb_trading.config.settings import ConfigManager
from arb_trading.exchanges.base import Direction


class TestArbitrageEngine:
    """ArbitrageEngine 테스트"""

    @pytest.fixture
    def mock_config(self):
        """목 설정 생성"""
        config = MagicMock(spec=ConfigManager)

        # trading config
        config.trading = MagicMock()
        config.trading.simulation_mode = True
        config.trading.max_positions = 3
        config.trading.target_usdt = 100
        config.trading.spread_threshold = 0.5
        config.trading.exit_percent = 0.5
        config.trading.spread_hold_count = 3
        config.trading.top_symbol_limit = 300
        config.trading.min_volume_usdt = 5000000

        # exchanges config
        config.exchanges = {
            'binance': MagicMock(),
            'bybit': MagicMock()
        }
        config.exchanges['binance'].enabled = True
        config.exchanges['binance'].fetch_only = False
        config.exchanges['binance'].api_key = "test"
        config.exchanges['binance'].secret = "test"
        config.exchanges['bybit'].enabled = True
        config.exchanges['bybit'].fetch_only = True
        config.exchanges['bybit'].api_key = "test"
        config.exchanges['bybit'].secret = "test"

        # orders config
        config.orders = MagicMock()
        config.orders.default_type = "limit"
        config.orders.market_order_enabled = False
        config.orders.limit_order_slippage = 0.001

        # monitoring config
        config.monitoring = MagicMock()
        config.monitoring.performance_logging = False
        config.monitoring.fetch_interval = 5
        config.monitoring.log_buffer_size = 100

        # notifications config
        config.notifications = MagicMock()
        config.notifications.slack_webhook = ""
        config.notifications.telegram_token = ""
        config.notifications.telegram_chat_id = ""
        config.notifications.email_smtp = ""

        # risk config
        config.risk = MagicMock()
        config.risk.max_loss_percent = -10
        config.risk.position_timeout_seconds = 300
        config.risk.order_timeout_seconds = 60

        return config

    @pytest.fixture
    def arbitrage_engine(self, mock_config):
        """ArbitrageEngine 인스턴스 생성"""
        return ArbitrageEngine(mock_config)

    def test_initialization(self, arbitrage_engine):
        """초기화 테스트"""
        assert arbitrage_engine.is_running == False
        assert arbitrage_engine.exchanges == {}
        assert arbitrage_engine.spread_monitor is None
        assert arbitrage_engine.position_manager is None


class TestSpreadMonitor:
    """SpreadMonitor 테스트"""

    @pytest.fixture
    def mock_exchanges(self):
        """목 거래소들 생성"""
        binance = AsyncMock()
        binance.name = "binance"
        binance.fetch_symbols.return_value = ["BTCUSDT", "ETHUSDT"]
        binance.fetch_tickers.return_value = {
            "BTCUSDT": MagicMock(last_price=50000.0),
            "ETHUSDT": MagicMock(last_price=3000.0)
        }
        binance.fetch_24h_volumes.return_value = {
            "BTCUSDT": 10000000.0,
            "ETHUSDT": 8000000.0
        }

        bybit = AsyncMock()
        bybit.name = "bybit"
        bybit.fetch_symbols.return_value = ["BTCUSDT", "ETHUSDT"]
        bybit.fetch_tickers.return_value = {
            "BTCUSDT": MagicMock(last_price=50050.0),  # 0.1% 스프레드
            "ETHUSDT": MagicMock(last_price=2985.0)  # 0.5% 스프레드
        }
        bybit.fetch_24h_volumes.return_value = {
            "BTCUSDT": 9500000.0,
            "ETHUSDT": 7500000.0
        }

        return {"binance": binance, "bybit": bybit}

    @pytest.fixture
    def spread_monitor(self, mock_exchanges):
        """SpreadMonitor 인스턴스 생성"""
        return SpreadMonitor(
            exchanges=mock_exchanges,
            min_volume_usdt=5000000,
            top_symbol_limit=10
        )

    @pytest.mark.asyncio
    async def test_get_common_symbols(self, spread_monitor):
        """공통 심볼 조회 테스트"""
        symbols = await spread_monitor.get_common_symbols()
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    @pytest.mark.asyncio
    async def test_fetch_spread_data(self, spread_monitor):
        """스프레드 데이터 조회 테스트"""
        spread_data = await spread_monitor.fetch_spread_data()

        assert len(spread_data) > 0
        assert isinstance(spread_data[0], SpreadData)

        # ETHUSDT가 더 큰 스프레드를 가져야 함
        eth_spread = next((s for s in spread_data if s.symbol == "ETHUSDT"), None)
        assert eth_spread is not None
        assert eth_spread.abs_spread_pct > 0.4  # 약 0.5% 스프레드


class TestPositionManager:
    """PositionManager 테스트"""

    @pytest.fixture
    def position_manager(self):
        """PositionManager 인스턴스 생성"""
        return PositionManager(max_positions=3)

    @pytest.fixture
    def mock_position(self):
        """목 포지션 생성"""
        long_exchange = MagicMock()
        short_exchange = MagicMock()

        return ArbitragePosition(
            symbol="BTCUSDT",
            long_exchange=long_exchange,
            short_exchange=short_exchange,
            long_symbol="BTCUSDT",
            short_symbol="BTCUSDT",
            quantity=1.0,
            entry_spread=0.5,
            entry_spread_signed=0.5,
            entry_timestamp=1234567890.0
        )

    def test_can_open_position(self, position_manager):
        """포지션 개설 가능 여부 테스트"""
        assert position_manager.can_open_position() == True

        # 최대 개수만큼 추가
        for i in range(3):
            position = MagicMock()
            position.status = PositionStatus.OPEN
            position_manager.positions[f"TEST{i}"] = position

        assert position_manager.can_open_position() == False

    def test_add_position(self, position_manager, mock_position):
        """포지션 추가 테스트"""
        result = position_manager.add_position(mock_position)
        assert result == True
        assert "BTCUSDT" in position_manager.positions

        # 중복 추가 시 실패해야 함
        result = position_manager.add_position(mock_position)
        assert result == False

    def test_position_summary(self, position_manager, mock_position):
        """포지션 요약 테스트"""
        position_manager.add_position(mock_position)

        summary = position_manager.get_position_summary()
        assert summary["총 포지션 수"] == 1
        assert summary["최대 포지션 수"] == 3
        assert summary["가용 슬롯"] == 2
