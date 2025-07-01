# arb_trading/exchanges/base.py (수정된 버전)
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import asyncio
import aiohttp
import time
import platform
from ..utils.platform_utils import get_optimal_connector


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class Direction(Enum):
    BINANCE_GT_BYBIT = "binance_gt_bybit"
    BYBIT_GT_BINANCE = "bybit_gt_binance"


@dataclass
class Ticker:
    symbol: str
    last_price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume_24h: float = 0.0
    timestamp: int = 0


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    amount: float
    price: Optional[float]
    filled: float = 0.0
    average: Optional[float] = None
    status: str = "open"
    timestamp: int = 0


@dataclass
class Position:
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    pnl: float = 0.0
    percentage: float = 0.0


class BaseExchange(ABC):
    """거래소 공통 인터페이스"""

    def __init__(self, api_key: str = "", secret: str = ""):
        """
        거래소 초기화 (testnet 제거)

        Args:
            api_key: API 키 (시뮬레이션에서는 빈 문자열 가능)
            secret: API 시크릿 (시뮬레이션에서는 빈 문자열 가능)
        """
        self.api_key = api_key
        self.secret = secret
        self.session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_delay = 0.1  # 기본 레이트 리미트

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        """연결 설정"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)

            # Windows 호환 커넥터 사용
            connector = get_optimal_connector()

            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'ArbitrageBot/1.0',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            )

    async def disconnect(self):
        """연결 해제"""
        if self.session:
            await self.session.close()
            self.session = None

    # 추상 메소드들 (기존과 동일)
    @abstractmethod
    async def fetch_tickers(self) -> Dict[str, Ticker]:
        """모든 티커 정보 조회"""
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """단일 티커 정보 조회"""
        pass

    @abstractmethod
    async def fetch_24h_volumes(self) -> Dict[str, float]:
        """24시간 거래량 조회"""
        pass

    @abstractmethod
    async def fetch_symbols(self) -> List[str]:
        """거래 가능한 심볼 목록 조회"""
        pass

    @abstractmethod
    def normalize_symbol(self, raw_symbol: str) -> Optional[str]:
        """심볼 표준화"""
        pass

    @abstractmethod
    def calculate_quantity(self, symbol: str, price: float, target_usdt: float) -> float:
        """목표 USDT 기준 수량 계산"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """거래소 이름"""
        pass

    # 시뮬레이션에서만 사용하는 메소드들은 기본 구현 제공
    async def fetch_balance(self) -> Dict[str, float]:
        """잔고 조회 (시뮬레이션용)"""
        return {'USDT': 10000.0}

    async def create_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                           amount: float, price: Optional[float] = None,
                           params: Optional[Dict] = None) -> Order:
        """주문 생성 (시뮬레이션용)"""
        return Order(
            id=f"sim_{int(time.time())}",
            symbol=symbol,
            side=side,
            type=order_type,
            amount=amount,
            price=price,
            filled=amount,  # 시뮬레이션에서는 즉시 체결
            average=price,
            status='filled',
            timestamp=self._get_timestamp()
        )

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """주문 조회 (시뮬레이션용)"""
        return Order(
            id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=1.0,
            price=100.0,
            filled=1.0,
            average=100.0,
            status='filled',
            timestamp=self._get_timestamp()
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """주문 취소 (시뮬레이션용)"""
        return True

    async def fetch_positions(self) -> List[Position]:
        """포지션 조회 (시뮬레이션용)"""
        return []

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정 (시뮬레이션용)"""
        return True

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> bool:
        """마진 모드 설정 (시뮬레이션용)"""
        return True

    async def _request(self, method: str, url: str, params: Optional[Dict] = None,
                       data: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        """공통 HTTP 요청 처리"""
        if not self.session:
            await self.connect()

        # 레이트 리미트 적용
        await asyncio.sleep(self._rate_limit_delay)

        # 재시도 로직
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 요청 헤더 병합
                request_headers = {}
                if headers:
                    request_headers.update(headers)

                async with self.session.request(
                        method=method,
                        url=url,
                        params=params,
                        json=data,
                        headers=request_headers,
                        ssl=False  # SSL 검증 비활성화 (필요시)
                ) as response:

                    if response.status == 429:  # Too Many Requests
                        wait_time = 2 ** attempt  # 지수 백오프
                        await asyncio.sleep(wait_time)
                        continue

                    if response.status >= 400:
                        error_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"HTTP {response.status}: {error_text}"
                        )

                    return await response.json()

            except asyncio.TimeoutError:
                if attempt == max_retries - 1:
                    raise Exception(f"{self.name} API 타임아웃")
                await asyncio.sleep(1)

            except aiohttp.ClientConnectorError as e:
                if attempt == max_retries - 1:
                    raise Exception(f"{self.name} 연결 실패: {e}")
                await asyncio.sleep(2)

            except aiohttp.ClientError as e:
                if attempt == max_retries - 1:
                    raise Exception(f"{self.name} API 요청 실패: {e}")
                await asyncio.sleep(1)

            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"{self.name} 예상치 못한 오류: {e}")
                await asyncio.sleep(1)

        raise Exception(f"{self.name} API 요청 최대 재시도 초과")

    def _get_timestamp(self) -> int:
        """현재 타임스탬프 반환 (밀리초)"""
        return int(time.time() * 1000)
