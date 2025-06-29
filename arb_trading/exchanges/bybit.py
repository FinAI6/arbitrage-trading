# arb_trading/exchanges/bybit.py (영구계약만 필터링)
import hashlib
import hmac
import urllib.parse
import json
from typing import Dict, List, Optional
from .base import BaseExchange, Ticker, Order, Position, OrderType, OrderSide
import asyncio
import logging


class BybitExchange(BaseExchange):
    """바이빗 선물 거래소 구현"""

    def __init__(self, api_key: str = "", secret: str = ""):
        super().__init__(api_key, secret)

        # 항상 실제 메인넷 사용
        self.base_url = "https://api.bybit.com"

        self._rate_limit_delay = 0.1
        self._symbols_cache = {}
        self._market_info = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def name(self) -> str:
        return "bybit"

    def _safe_float(self, value, default: float = 0.0) -> float:
        """안전한 float 변환"""
        if value is None or value == '' or value == '0':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _is_perpetual_contract(self, symbol: str) -> bool:
        """영구계약인지 확인 (만료일이 없는 계약)"""
        # 영구계약은 단순히 BTCUSDT, ETHUSDT 형태
        # 선물계약은 BTCUSDT-04JUL25, BTCUSDT-26DEC25 형태

        if '-' in symbol:
            return False  # 만료일이 있는 선물계약

        # USDT로 끝나는 영구계약만 허용
        if symbol.endswith('USDT'):
            return True

        return False

    async def fetch_tickers(self) -> Dict[str, Ticker]:
        """모든 티커 정보 조회 (영구계약만)"""
        try:
            url = f"{self.base_url}/v5/market/tickers"
            params = {'category': 'linear'}
            data = await self._request("GET", url, params=params)

            if data.get('retCode') != 0:
                raise Exception(f"바이빗 API 오류: {data.get('retMsg')}")

            result_list = data.get('result', {}).get('list', [])

            tickers = {}
            perpetual_count = 0
            futures_count = 0

            for item in result_list:
                try:
                    symbol = item['symbol']

                    # 영구계약만 필터링
                    if not self._is_perpetual_contract(symbol):
                        futures_count += 1
                        continue

                    perpetual_count += 1

                    # 가격 추출
                    last_price = float(item['lastPrice'])

                    if last_price <= 0:
                        self.logger.debug(f"{symbol}: 유효하지 않은 lastPrice ({last_price})")
                        continue

                    bid_price = self._safe_float(item.get('bid1Price'))
                    ask_price = self._safe_float(item.get('ask1Price'))
                    volume_24h = self._safe_float(item.get('turnover24h'))

                    # 디버깅: 주요 심볼들의 가격 출력
                    if symbol in ['BTCUSDT', 'ETHUSDT', 'ADAUSDT']:
                        self.logger.info(
                            f"바이빗 {symbol}: last={last_price}, bid={bid_price}, ask={ask_price}"
                        )

                    tickers[symbol] = Ticker(
                        symbol=symbol,
                        last_price=last_price,
                        bid=bid_price if bid_price > 0 else None,
                        ask=ask_price if ask_price > 0 else None,
                        volume_24h=volume_24h,
                        timestamp=self._get_timestamp()
                    )

                except (KeyError, ValueError, TypeError) as e:
                    self.logger.debug(f"티커 파싱 실패 ({item.get('symbol', 'Unknown')}): {e}")
                    continue

            self.logger.info(
                f"바이빗 티커 조회 완료: {len(tickers)}개 영구계약 "
                f"(전체: {perpetual_count + futures_count}개, 선물 제외: {futures_count}개)"
            )

            return tickers

        except Exception as e:
            self.logger.error(f"바이빗 티커 조회 실패: {e}")
            raise Exception(f"바이빗 티커 조회 실패: {e}")

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """단일 티커 정보 조회"""
        try:
            # 영구계약인지 먼저 확인
            if not self._is_perpetual_contract(symbol):
                raise Exception(f"영구계약이 아님: {symbol}")

            url = f"{self.base_url}/v5/market/tickers"
            params = {'category': 'linear', 'symbol': symbol}
            data = await self._request("GET", url, params=params)

            if data.get('retCode') != 0:
                raise Exception(f"바이빗 API 오류: {data.get('retMsg')}")

            items = data.get('result', {}).get('list', [])
            if not items:
                raise Exception(f"심볼을 찾을 수 없음: {symbol}")

            item = items[0]

            # 원시 데이터 로깅 (디버깅용)
            self.logger.debug(f"바이빗 {symbol} 원시 데이터:")
            self.logger.debug(f"  lastPrice: {item.get('lastPrice')}")
            self.logger.debug(f"  markPrice: {item.get('markPrice')}")
            self.logger.debug(f"  indexPrice: {item.get('indexPrice')}")
            self.logger.debug(f"  bid1Price: {item.get('bid1Price')}")
            self.logger.debug(f"  ask1Price: {item.get('ask1Price')}")

            last_price = float(item['lastPrice'])

            if last_price <= 0:
                raise Exception(f"유효하지 않은 가격: {symbol} -> {last_price}")

            return Ticker(
                symbol=symbol,
                last_price=last_price,
                bid=self._safe_float(item.get('bid1Price')),
                ask=self._safe_float(item.get('ask1Price')),
                volume_24h=self._safe_float(item.get('turnover24h')),
                timestamp=self._get_timestamp()
            )

        except Exception as e:
            self.logger.error(f"바이빗 단일 티커 조회 실패 ({symbol}): {e}")
            raise Exception(f"바이빗 단일 티커 조회 실패 ({symbol}): {e}")

    async def fetch_24h_volumes(self) -> Dict[str, float]:
        """24시간 거래량 조회 (영구계약만)"""
        try:
            tickers = await self.fetch_tickers()  # 이미 영구계약만 필터링됨
            volumes = {}

            for symbol, ticker in tickers.items():
                if ticker.volume_24h > 0:
                    volumes[symbol] = ticker.volume_24h

            self.logger.info(f"바이빗 거래량 조회 완료: {len(volumes)}개")
            return volumes

        except Exception as e:
            self.logger.error(f"바이빗 거래량 조회 실패: {e}")
            raise Exception(f"바이빗 거래량 조회 실패: {e}")

    async def fetch_symbols(self) -> List[str]:
        """거래 가능한 심볼 목록 조회 (영구계약만)"""
        if self._symbols_cache:
            return list(self._symbols_cache.keys())

        try:
            url = f"{self.base_url}/v5/market/instruments-info"
            params = {'category': 'linear'}
            data = await self._request("GET", url, params=params)

            if data.get('retCode') != 0:
                raise Exception(f"바이빗 API 오류: {data.get('retMsg')}")

            symbols = []
            perpetual_count = 0
            futures_count = 0

            for item in data.get('result', {}).get('list', []):
                symbol = item.get('symbol', '')

                # 영구계약 필터링
                if not self._is_perpetual_contract(symbol):
                    futures_count += 1
                    continue

                # 추가 조건: USDT 영구계약, 거래 중
                if (item.get('quoteCoin') == 'USDT' and
                        item.get('status') == 'Trading' and
                        item.get('contractType') == 'LinearPerpetual'):
                    symbols.append(symbol)
                    perpetual_count += 1

                    # 마켓 정보 캐시
                    lot_size_filter = item.get('lotSizeFilter', {})
                    price_filter = item.get('priceFilter', {})

                    self._market_info[symbol] = {
                        'min_qty': self._safe_float(lot_size_filter.get('minOrderQty', '0.001')),
                        'qty_step': self._safe_float(lot_size_filter.get('qtyStep', '0.001')),
                        'tick_size': self._safe_float(price_filter.get('tickSize', '0.01'))
                    }

            self._symbols_cache = {s: s for s in symbols}
            self.logger.info(
                f"바이빗 심볼 조회 완료: {len(symbols)}개 영구계약 "
                f"(전체: {perpetual_count + futures_count}개, 선물 제외: {futures_count}개)"
            )

            # 주요 심볼들이 포함되었는지 확인
            major_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'SOLUSDT']
            found_majors = [s for s in major_symbols if s in symbols]
            self.logger.info(f"주요 심볼 포함: {found_majors}")

            return symbols

        except Exception as e:
            self.logger.error(f"바이빗 심볼 조회 실패: {e}")
            raise Exception(f"바이빗 심볼 조회 실패: {e}")

    def normalize_symbol(self, raw_symbol: str) -> Optional[str]:
        """심볼 표준화"""
        formatted = raw_symbol.replace('/', '').replace(':', '').upper()

        # 영구계약인지 확인
        if not self._is_perpetual_contract(formatted):
            return None

        return self._symbols_cache.get(formatted)

    def calculate_quantity(self, symbol: str, price: float, target_usdt: float) -> float:
        """목표 USDT 기준 수량 계산"""
        qty = target_usdt / price

        if symbol in self._market_info:
            min_qty = self._market_info[symbol]['min_qty']
            if qty < min_qty:
                qty = min_qty

        return qty

    # 시뮬레이션용 메소드들
    async def fetch_balance(self) -> Dict[str, float]:
        return {'USDT': 10000.0}

    async def create_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                           amount: float, price: Optional[float] = None,
                           params: Optional[Dict] = None) -> Order:
        return Order(
            id="sim_order_123",
            symbol=symbol,
            side=side,
            type=order_type,
            amount=amount,
            price=price,
            filled=amount,
            average=price,
            status='filled',
            timestamp=self._get_timestamp()
        )

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
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
        return True

    async def fetch_positions(self) -> List[Position]:
        return []

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        return True

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> bool:
        return True
