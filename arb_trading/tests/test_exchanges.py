# arb_trading/tests/test_exchanges.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from arb_trading.exchanges.base import BaseExchange, OrderType, OrderSide, Ticker
from arb_trading.exchanges.binance import BinanceExchange
from arb_trading.exchanges.bybit import BybitExchange


class TestBaseExchange:
    """BaseExchange 테스트"""

    @pytest.fixture
    def mock_exchange(self):
        """목 거래소 생성"""

        class MockExchange(BaseExchange):
            @property
            def name(self):
                return "mock"

            async def fetch_tickers(self):
                return {"BTCUSDT": Ticker("BTCUSDT", 50000.0)}

            async def fetch_ticker(self, symbol):
                return Ticker(symbol, 50000.0)

            async def fetch_24h_volumes(self):
                return {"BTCUSDT": 1000000.0}

            async def fetch_symbols(self):
                return ["BTCUSDT", "ETHUSDT"]

            async def fetch_balance(self):
                return {"USDT": 1000.0}

            async def create_order(self, symbol, side, order_type, amount, price=None, params=None):
                from arb_trading.exchanges.base import Order
                return Order("12345", symbol, side, order_type, amount, price)

            async def fetch_order(self, order_id, symbol):
                from arb_trading.exchanges.base import Order
                return Order(order_id, symbol, OrderSide.BUY, OrderType.LIMIT, 1.0, 50000.0)

            async def cancel_order(self, order_id, symbol):
                return True

            async def fetch_positions(self):
                return []

            async def set_leverage(self, symbol, leverage):
                return True

            async def set_margin_mode(self, symbol, margin_mode):
                return True

            def normalize_symbol(self, raw_symbol):
                return raw_symbol.upper()

            def calculate_quantity(self, symbol, price, target_usdt):
                return target_usdt / price

        return MockExchange("test_key", "test_secret")

    @pytest.mark.asyncio
    async def test_connection_lifecycle(self, mock_exchange):
        """연결 생명주기 테스트"""
        async with mock_exchange:
            assert mock_exchange.session is not None

        # 연결 해제 후에는 session이 None이어야 함
        assert mock_exchange.session is None

    @pytest.mark.asyncio
    async def test_fetch_tickers(self, mock_exchange):
        """티커 조회 테스트"""
        async with mock_exchange:
            tickers = await mock_exchange.fetch_tickers()
            assert "BTCUSDT" in tickers
            assert tickers["BTCUSDT"].last_price == 50000.0


class TestBinanceExchange:
    """BinanceExchange 테스트"""

    @pytest.fixture
    def binance_exchange(self):
        return BinanceExchange("test_key", "test_secret")

    def test_initialization(self, binance_exchange):
        """초기화 테스트"""
        assert binance_exchange.name == "binance"

    def test_symbol_normalization(self, binance_exchange):
        """심볼 표준화 테스트"""
        # 캐시가 없는 상태에서는 None 반환
        result = binance_exchange.normalize_symbol("BTC/USDT")
        assert result is None

    def test_quantity_calculation(self, binance_exchange):
        """수량 계산 테스트"""
        quantity = binance_exchange.calculate_quantity("BTCUSDT", 50000.0, 1000.0)
        assert quantity == 0.02  # 1000 / 50000


class TestBybitExchange:
    """BybitExchange 테스트"""

    @pytest.fixture
    def bybit_exchange(self):
        return BybitExchange("test_key", "test_secret")

    def test_initialization(self, bybit_exchange):
        """초기화 테스트"""
        assert bybit_exchange.name == "bybit"

    def test_quantity_calculation(self, bybit_exchange):
        """수량 계산 테스트"""
        quantity = bybit_exchange.calculate_quantity("BTCUSDT", 50000.0, 1000.0)
        assert quantity == 0.02  # 1000 / 50000
