# arb_trading/core/spread_monitor.py (디버깅 강화 버전)
import asyncio
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict, deque
from ..exchanges.base import BaseExchange, Ticker, Direction
from ..utils.performance import PerformanceMonitor
import logging


@dataclass
class SpreadData:
    """스프레드 데이터"""
    timestamp: str
    symbol: str
    binance_price: float
    bybit_price: float
    spread_pct: float
    abs_spread_pct: float
    direction: Direction
    volume_24h: float


class SpreadMonitor:
    """스프레드 모니터링 클래스"""

    def __init__(self, exchanges: Dict[str, BaseExchange],
                 min_volume_usdt: float = 5000000,
                 top_symbol_limit: int = 300,
                 performance_monitor: Optional[PerformanceMonitor] = None):

        self.exchanges = exchanges
        self.min_volume_usdt = min_volume_usdt
        self.top_symbol_limit = top_symbol_limit
        self.performance_monitor = performance_monitor
        self.logger = logging.getLogger(__name__)

        # 캐시된 데이터
        self._symbols_cache: Optional[List[str]] = None
        self._last_symbols_update = 0
        self._symbols_cache_ttl = 3600  # 1시간

    async def get_common_symbols(self) -> List[str]:
        """공통 거래 가능 심볼 조회 (캐시 활용)"""
        now = time.time()

        if (self._symbols_cache is None or
                now - self._last_symbols_update > self._symbols_cache_ttl):

            start_time = time.time()

            try:
                # 모든 거래소에서 심볼 목록 동시 조회
                tasks = []
                for name, exchange in self.exchanges.items():
                    tasks.append(self._fetch_symbols_with_name(name, exchange))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 결과 처리
                exchange_symbols = {}
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"심볼 조회 실패: {result}")
                        continue
                    name, symbols = result
                    exchange_symbols[name] = set(symbols)
                    self.logger.debug(f"{name} 심볼 수: {len(symbols)}")

                if len(exchange_symbols) < 2:
                    raise Exception("최소 2개 거래소의 심볼이 필요합니다")

                # 공통 심볼 찾기
                common_symbols = set.intersection(*exchange_symbols.values())
                self.logger.info(f"거래소간 공통 심볼: {len(common_symbols)}개")

                # 거래량 기준 필터링
                volumes = await self._get_volumes_data()

                # 거래량 조건을 만족하는 심볼들
                volume_filtered = []
                for s in common_symbols:
                    max_volume = max(
                        volumes.get(exchange_name, {}).get(s, 0)
                        for exchange_name in volumes.keys()
                    )
                    if max_volume >= self.min_volume_usdt:
                        volume_filtered.append(s)

                self.logger.info(f"거래량 조건 통과: {len(volume_filtered)}개 (최소: {self.min_volume_usdt:,} USDT)")

                # 거래량 기준 정렬 후 상위 N개 선택
                def get_max_volume(symbol):
                    return max(volumes.get(exchange_name, {}).get(symbol, 0)
                               for exchange_name in volumes.keys())

                volume_ranked = sorted(volume_filtered, key=get_max_volume, reverse=True)
                self._symbols_cache = volume_ranked[:self.top_symbol_limit]
                self._last_symbols_update = now

                if self.performance_monitor:
                    self.performance_monitor.record_fetch_time(time.time() - start_time)

                self.logger.info(f"최종 사용 심볼: {len(self._symbols_cache)}개")

                # 상위 10개 심볼과 거래량 출력 (디버깅용)
                self.logger.debug("상위 10개 심볼:")
                for i, symbol in enumerate(self._symbols_cache[:10]):
                    volume = get_max_volume(symbol)
                    self.logger.debug(f"  {i + 1}. {symbol}: {volume:,.0f} USDT")

            except Exception as e:
                self.logger.error(f"심볼 조회 중 오류: {e}")
                if self._symbols_cache is None:
                    self._symbols_cache = []

        return self._symbols_cache

    async def _fetch_symbols_with_name(self, name: str, exchange: BaseExchange) -> Tuple[str, List[str]]:
        """거래소별 심볼 조회 (이름 포함)"""
        if self.performance_monitor:
            self.performance_monitor.record_api_call(name)

        symbols = await exchange.fetch_symbols()
        return name, symbols

    async def _get_volumes_data(self) -> Dict[str, Dict[str, float]]:
        """모든 거래소에서 거래량 데이터 조회"""
        tasks = []
        for name, exchange in self.exchanges.items():
            tasks.append(self._fetch_volumes_with_name(name, exchange))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        volumes = {}
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"거래량 조회 실패: {result}")
                continue
            name, volume_data = result
            volumes[name] = volume_data
            self.logger.debug(f"{name} 거래량 데이터: {len(volume_data)}개")

        return volumes

    async def _fetch_volumes_with_name(self, name: str, exchange: BaseExchange) -> Tuple[str, Dict[str, float]]:
        """거래소별 거래량 조회 (이름 포함)"""
        if self.performance_monitor:
            self.performance_monitor.record_api_call(name)

        volumes = await exchange.fetch_24h_volumes()
        return name, volumes

    def _validate_price_pair(self, symbol: str, binance_price: float, bybit_price: float) -> bool:
        """가격 쌍 유효성 검사"""
        # 기본 검사
        if binance_price <= 0 or bybit_price <= 0:
            self.logger.warning(f"{symbol}: 유효하지 않은 가격 - B:{binance_price}, Y:{bybit_price}")
            return False

        # 극단적 차이 검사 (10배 이상 차이)
        ratio = max(binance_price, bybit_price) / min(binance_price, bybit_price)
        if ratio > 10.0:
            self.logger.warning(f"{symbol}: 극단적 가격 차이 - B:{binance_price}, Y:{bybit_price} (비율: {ratio:.2f})")
            return False

        # 가격대별 현실성 검사
        avg_price = (binance_price + bybit_price) / 2
        spread_pct = abs(binance_price - bybit_price) / min(binance_price, bybit_price) * 100

        # 가격대별 최대 허용 스프레드
        if avg_price >= 1000:  # 고가 코인 (BTC 등)
            max_spread = 1.0  # 1%
        elif avg_price >= 10:  # 중가 코인 (ETH 등)
            max_spread = 2.0  # 2%
        elif avg_price >= 0.1:  # 저가 코인
            max_spread = 5.0  # 5%
        else:  # 극저가 코인
            max_spread = 10.0  # 10%

        if spread_pct > max_spread:
            self.logger.warning(
                f"{symbol}: 비현실적 스프레드 - B:{binance_price}, Y:{bybit_price} "
                f"({spread_pct:.2f}% > 최대 {max_spread}%)"
            )
            return False

        return True

    async def fetch_spread_data(self) -> List[SpreadData]:
        """스프레드 데이터 조회 (상세 성능 로깅)"""
        cycle_start_time = time.time()

        try:
            # 성능 모니터링 사이클 시작
            if self.performance_monitor:
                self.performance_monitor.start_fetch_cycle()

            # 공통 심볼 조회
            symbols = await self.get_common_symbols()
            if not symbols:
                return []

            # 데이터 페치 시작
            fetch_start_time = time.time()

            # 모든 거래소에서 가격 데이터 동시 조회 (개별 타이밍 측정)
            tasks = []
            for name, exchange in self.exchanges.items():
                tasks.append(self._fetch_tickers_with_timing(name, exchange))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            fetch_end_time = time.time()
            fetch_duration = fetch_end_time - fetch_start_time

            # 가격 데이터 정리
            exchange_prices = {}
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"가격 조회 실패: {result}")
                    continue
                name, tickers = result
                exchange_prices[name] = {symbol: ticker.last_price for symbol, ticker in tickers.items()}

            if len(exchange_prices) < 2:
                self.logger.warning("충분한 가격 데이터를 조회할 수 없습니다")
                return []

            # 스프레드 계산 시작
            calc_start_time = time.time()
            spread_list = []

            for symbol in symbols:
                # 가격 데이터 수집
                prices = {}
                for exchange_name in exchange_prices:
                    if symbol in exchange_prices[exchange_name]:
                        prices[exchange_name] = exchange_prices[exchange_name][symbol]

                if len(prices) < 2:
                    continue

                # 바이낸스와 바이빗 가격
                binance_price = prices.get('binance')
                bybit_price = prices.get('bybit')

                if binance_price and bybit_price and binance_price > 0 and bybit_price > 0:
                    # 스프레드 계산
                    higher_price = max(binance_price, bybit_price)
                    lower_price = min(binance_price, bybit_price)
                    abs_spread_pct = (higher_price - lower_price) / lower_price * 100

                    # 방향성 고려
                    if binance_price > bybit_price:
                        spread_pct = abs_spread_pct
                        direction = Direction.BINANCE_GT_BYBIT
                    else:
                        spread_pct = -abs_spread_pct
                        direction = Direction.BYBIT_GT_BINANCE

                    # 현실적인 스프레드만 포함 (5% 이하)
                    if abs_spread_pct <= 5.0:
                        spread_list.append(SpreadData(
                            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                            symbol=symbol,
                            binance_price=binance_price,
                            bybit_price=bybit_price,
                            spread_pct=spread_pct,
                            abs_spread_pct=abs_spread_pct,
                            direction=direction,
                            volume_24h=0.0
                        ))

            # 절대값 스프레드 기준으로 정렬
            spread_list.sort(key=lambda x: x.abs_spread_pct, reverse=True)

            calc_end_time = time.time()
            calc_duration = calc_end_time - calc_start_time
            total_duration = calc_end_time - cycle_start_time

            # 성능 기록
            if self.performance_monitor:
                self.performance_monitor.record_fetch_time(fetch_duration)
                self.performance_monitor.record_spread_calc_time(calc_duration, len(spread_list))
                self.performance_monitor.record_total_cycle_time(
                    total_duration, fetch_duration, calc_duration, len(spread_list)
                )

            return spread_list

        except Exception as e:
            self.logger.error(f"스프레드 데이터 조회 실패: {e}")
            if self.performance_monitor:
                self.performance_monitor.record_error("spread_fetch_error")
            return []

    async def _fetch_tickers_with_timing(self, name: str, exchange: BaseExchange) -> Tuple[str, Dict[str, Ticker]]:
        """거래소별 티커 조회 (타이밍 측정)"""
        start_time = time.time()

        try:
            if self.performance_monitor:
                self.performance_monitor.record_api_call(name)

            tickers = await exchange.fetch_tickers()

            duration = time.time() - start_time
            if self.performance_monitor:
                self.performance_monitor.record_exchange_fetch(
                    name, "tickers", duration, success=True
                )

            return name, tickers

        except Exception as e:
            duration = time.time() - start_time
            if self.performance_monitor:
                self.performance_monitor.record_exchange_fetch(
                    name, "tickers", duration, success=False, error_msg=str(e)
                )
            raise

    async def _fetch_tickers_with_name(self, name: str, exchange: BaseExchange) -> Tuple[str, Dict[str, Ticker]]:
        """거래소별 티커 조회 (이름 포함)"""
        if self.performance_monitor:
            self.performance_monitor.record_api_call(name)

        tickers = await exchange.fetch_tickers()
        return name, tickers
