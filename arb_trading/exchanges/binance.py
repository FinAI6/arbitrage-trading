# arb_trading/exchanges/binance.py
import hashlib
import hmac
import urllib.parse
from typing import Dict, List, Optional
from .base import BaseExchange, Ticker, Order, Position, OrderType, OrderSide
import asyncio


class BinanceExchange(BaseExchange):
    """바이낸스 선물 거래소 구현"""

    def __init__(self, api_key: str, secret: str):
        super().__init__(api_key, secret)

        self.base_url = "https://fapi.binance.com"


        self._rate_limit_delay = 0.05  # 바이낸스는 빠른 요청 허용
        self._symbols_cache = {}
        self._market_info = {}

    @property
    def name(self) -> str:
        return "binance"

    def _sign_request(self, params: Dict) -> str:
        """요청 서명 생성"""
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _signed_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """서명된 요청"""
        if params is None:
            params = {}

        params['timestamp'] = self._get_timestamp()
        signature = self._sign_request(params)
        params['signature'] = signature

        headers = {
            'X-MBX-APIKEY': self.api_key
        }

        url = f"{self.base_url}{endpoint}"
        return await self._request(method, url, params=params, headers=headers)

    async def fetch_symbols(self) -> List[str]:
        """거래 가능한 심볼 목록 조회"""
        if self._symbols_cache:
            return list(self._symbols_cache.keys())

        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            data = await self._request("GET", url)

            symbols = []
            for item in data.get('symbols', []):
                if (item.get('contractType') == 'PERPETUAL' and
                        item.get('quoteAsset') == 'USDT' and
                        item.get('status') == 'TRADING'):

                    symbol = item['symbol']
                    symbols.append(symbol)

                    # 마켓 정보 캐시
                    self._market_info[symbol] = {
                        'base_precision': item.get('baseAssetPrecision', 8),
                        'quote_precision': item.get('quotePrecision', 8),
                        'min_qty': 0.001,  # 기본값
                        'tick_size': 0.01  # 기본값
                    }

                    # 필터에서 정확한 값 추출
                    for filter_item in item.get('filters', []):
                        if filter_item['filterType'] == 'LOT_SIZE':
                            self._market_info[symbol]['min_qty'] = float(filter_item['minQty'])
                        elif filter_item['filterType'] == 'PRICE_FILTER':
                            self._market_info[symbol]['tick_size'] = float(filter_item['tickSize'])

            self._symbols_cache = {s: s for s in symbols}
            return symbols

        except Exception as e:
            raise Exception(f"바이낸스 심볼 조회 실패: {e}")

    async def fetch_tickers(self) -> Dict[str, Ticker]:
        """모든 티커 정보 조회"""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            price_data = await self._request("GET", url)

            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            volume_data = await self._request("GET", url)

            # 가격과 볼륨 데이터 결합
            volume_dict = {item['symbol']: item for item in volume_data}

            tickers = {}
            for item in price_data:
                symbol = item['symbol']
                price = float(item['price'])

                volume_info = volume_dict.get(symbol, {})

                tickers[symbol] = Ticker(
                    symbol=symbol,
                    last_price=price,
                    bid=None,  # 별도 API 필요
                    ask=None,  # 별도 API 필요
                    volume_24h=float(volume_info.get('quoteVolume', 0)),
                    timestamp=self._get_timestamp()
                )

            return tickers

        except Exception as e:
            raise Exception(f"바이낸스 티커 조회 실패: {e}")

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """단일 티커 정보 조회"""
        try:
            # Book ticker로 bid/ask 포함해서 조회
            url = f"{self.base_url}/fapi/v1/ticker/bookTicker"
            data = await self._request("GET", url, params={'symbol': symbol})

            return Ticker(
                symbol=symbol,
                last_price=float(data['bidPrice']),  # 임시로 bid 사용
                bid=float(data['bidPrice']),
                ask=float(data['askPrice']),
                volume_24h=0.0,  # 별도 조회 필요
                timestamp=self._get_timestamp()
            )

        except Exception as e:
            raise Exception(f"바이낸스 단일 티커 조회 실패 ({symbol}): {e}")

    async def fetch_24h_volumes(self) -> Dict[str, float]:
        """24시간 거래량 조회"""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            data = await self._request("GET", url)

            return {
                item['symbol']: float(item.get('quoteVolume', 0))
                for item in data
            }

        except Exception as e:
            raise Exception(f"바이낸스 거래량 조회 실패: {e}")

    async def fetch_balance(self) -> Dict[str, float]:
        """잔고 조회"""
        try:
            data = await self._signed_request("GET", "/fapi/v2/balance")
            return {
                item['asset']: float(item['balance'])
                for item in data
                if float(item['balance']) > 0
            }

        except Exception as e:
            raise Exception(f"바이낸스 잔고 조회 실패: {e}")

    async def create_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                           amount: float, price: Optional[float] = None,
                           params: Optional[Dict] = None) -> Order:
        """주문 생성"""
        try:
            order_params = {
                'symbol': symbol,
                'side': side.value.upper(),
                'type': order_type.value.upper(),
                'quantity': self._format_quantity(symbol, amount)
            }

            if order_type == OrderType.LIMIT and price:
                order_params['price'] = self._format_price(symbol, price)
                order_params['timeInForce'] = 'GTC'  # Good Till Cancel

            if params:
                order_params.update(params)

            data = await self._signed_request("POST", "/fapi/v1/order", order_params)

            return Order(
                id=str(data['orderId']),
                symbol=symbol,
                side=side,
                type=order_type,
                amount=amount,
                price=price,
                filled=float(data.get('executedQty', 0)),
                average=float(data.get('avgPrice', 0)) if data.get('avgPrice') else None,
                status=data.get('status', 'NEW').lower(),
                timestamp=int(data.get('updateTime', self._get_timestamp()))
            )

        except Exception as e:
            raise Exception(f"바이낸스 주문 생성 실패 ({symbol}): {e}")

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """주문 조회"""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            data = await self._signed_request("GET", "/fapi/v1/order", params)

            return Order(
                id=str(data['orderId']),
                symbol=symbol,
                side=OrderSide.BUY if data['side'] == 'BUY' else OrderSide.SELL,
                type=OrderType.MARKET if data['type'] == 'MARKET' else OrderType.LIMIT,
                amount=float(data['origQty']),
                price=float(data['price']) if data['price'] != '0' else None,
                filled=float(data['executedQty']),
                average=float(data['avgPrice']) if data.get('avgPrice') and data['avgPrice'] != '0' else None,
                status=data['status'].lower(),
                timestamp=int(data['updateTime'])
            )

        except Exception as e:
            raise Exception(f"바이낸스 주문 조회 실패 ({order_id}): {e}")

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """주문 취소"""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            await self._signed_request("DELETE", "/fapi/v1/order", params)
            return True

        except Exception as e:
            raise Exception(f"바이낸스 주문 취소 실패 ({order_id}): {e}")

    async def fetch_positions(self) -> List[Position]:
        """포지션 조회"""
        try:
            data = await self._signed_request("GET", "/fapi/v2/positionRisk")

            positions = []
            for item in data:
                if float(item['positionAmt']) != 0:
                    positions.append(Position(
                        symbol=item['symbol'],
                        side='long' if float(item['positionAmt']) > 0 else 'short',
                        size=abs(float(item['positionAmt'])),
                        entry_price=float(item['entryPrice']),
                        mark_price=float(item['markPrice']),
                        pnl=float(item['unRealizedProfit']),
                        percentage=float(item['percentage'])
                    ))

            return positions

        except Exception as e:
            raise Exception(f"바이낸스 포지션 조회 실패: {e}")

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            params = {
                'symbol': symbol,
                'leverage': leverage
            }
            await self._signed_request("POST", "/fapi/v1/leverage", params)
            return True

        except Exception as e:
            if "leverage not modified" in str(e).lower():
                return True  # 이미 설정된 경우
            raise Exception(f"바이낸스 레버리지 설정 실패 ({symbol}): {e}")

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> bool:
        """마진 모드 설정"""
        try:
            params = {
                'symbol': symbol,
                'marginType': margin_mode.upper()  # ISOLATED 또는 CROSSED
            }
            await self._signed_request("POST", "/fapi/v1/marginType", params)
            return True

        except Exception as e:
            if "no need to change margin type" in str(e).lower():
                return True  # 이미 설정된 경우
            raise Exception(f"바이낸스 마진 모드 설정 실패 ({symbol}): {e}")

    def normalize_symbol(self, raw_symbol: str) -> Optional[str]:
        """심볼 표준화"""
        formatted = raw_symbol.replace('/', '').replace(':', '').upper()
        return self._symbols_cache.get(formatted)

    def calculate_quantity(self, symbol: str, price: float, target_usdt: float) -> float:
        """목표 USDT 기준 수량 계산"""
        qty = target_usdt / price

        if symbol in self._market_info:
            min_qty = self._market_info[symbol]['min_qty']
            if qty < min_qty:
                qty = min_qty

        return qty

    def _format_quantity(self, symbol: str, quantity: float) -> str:
        """수량 포맷팅 (round 제거)"""
        return str(quantity)  # round() 없이 그대로 문자열 변환

    def _format_price(self, symbol: str, price: float) -> str:
        """가격 포맷팅 (round 제거)"""
        return str(price)  # round() 없이 그대로 문자열 변환
