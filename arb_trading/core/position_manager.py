# arb_trading/core/position_manager.py
import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from ..exchanges.base import BaseExchange, Order, Position, OrderSide, OrderType, Direction
from ..utils.notifications import NotificationManager
import logging


class PositionStatus(Enum):
    PENDING = "pending"  # 진입 대기중
    OPEN = "open"  # 포지션 오픈
    CLOSING = "closing"  # 청산 중
    CLOSED = "closed"  # 청산 완료


@dataclass
class ArbitragePosition:
    """차익거래 포지션"""
    symbol: str
    long_exchange: BaseExchange
    short_exchange: BaseExchange
    long_symbol: str
    short_symbol: str
    quantity: float
    entry_spread: float
    entry_spread_signed: float
    entry_timestamp: float
    status: PositionStatus = PositionStatus.PENDING

    # 주문 정보
    long_order_id: Optional[str] = None
    short_order_id: Optional[str] = None
    long_filled: float = 0.0
    short_filled: float = 0.0

    # 진입 가격
    long_entry_price: Optional[float] = None
    short_entry_price: Optional[float] = None

    # 청산 정보
    exit_timestamp: Optional[float] = None
    exit_spread: Optional[float] = None
    pnl: float = 0.0


class PositionManager:
    """포지션 관리 클래스"""

    def __init__(self, max_positions: int = 3,
                 position_timeout: int = 300,
                 order_timeout: int = 60,
                 notification_manager: Optional[NotificationManager] = None):

        self.max_positions = max_positions
        self.position_timeout = position_timeout
        self.order_timeout = order_timeout
        self.notification_manager = notification_manager
        self.logger = logging.getLogger(__name__)

        self.positions: Dict[str, ArbitragePosition] = {}

    def can_open_position(self) -> bool:
        """새 포지션 개설 가능 여부"""
        open_count = len([p for p in self.positions.values()
                          if p.status in [PositionStatus.PENDING, PositionStatus.OPEN]])
        return open_count < self.max_positions

    def add_position(self, position: ArbitragePosition) -> bool:
        """포지션 추가"""
        if not self.can_open_position():
            self.logger.warning(f"최대 포지션 수({self.max_positions}) 도달로 인해 {position.symbol} 포지션 개설 불가")
            return False

        if position.symbol in self.positions:
            self.logger.warning(f"이미 존재하는 포지션: {position.symbol}")
            return False

        self.positions[position.symbol] = position
        self.logger.info(f"새 포지션 추가: {position.symbol} (총 {len(self.positions)}개)")

        if self.notification_manager:
            asyncio.create_task(self.notification_manager.send_slack_notification(
                f"새 차익거래 포지션 개설: {position.symbol}\n"
                f"진입 스프레드: {position.entry_spread_signed:+.2f}%\n"
                f"롱: {position.long_exchange.name} | 숏: {position.short_exchange.name}"
            ))

        return True

    async def update_position_status(self, symbol: str) -> bool:
        """포지션 상태 업데이트"""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        try:
            # 주문 상태 확인
            if position.status == PositionStatus.PENDING:
                long_filled = 0.0
                short_filled = 0.0

                if position.long_order_id:
                    long_order = await position.long_exchange.fetch_order(
                        position.long_order_id, position.long_symbol
                    )
                    long_filled = long_order.filled
                    if long_order.average:
                        position.long_entry_price = long_order.average

                if position.short_order_id:
                    short_order = await position.short_exchange.fetch_order(
                        position.short_order_id, position.short_symbol
                    )
                    short_filled = short_order.filled
                    if short_order.average:
                        position.short_entry_price = short_order.average

                position.long_filled = long_filled
                position.short_filled = short_filled

                # 양쪽 모두 체결된 경우
                if long_filled > 0 and short_filled > 0:
                    position.status = PositionStatus.OPEN
                    self.logger.info(f"포지션 체결 완료: {symbol}")

                    if self.notification_manager:
                        await self.notification_manager.send_slack_notification(
                            f"포지션 체결 완료: {symbol}\n"
                            f"롱: {long_filled:.4f} @ {position.long_entry_price or 'N/A'}\n"
                            f"숏: {short_filled:.4f} @ {position.short_entry_price or 'N/A'}"
                        )

                # 한쪽만 체결된 경우 타임아웃 체크
                elif (long_filled > 0 or short_filled > 0) and \
                        time.time() - position.entry_timestamp > self.order_timeout:

                    await self._handle_partial_fill(position)

            return True

        except Exception as e:
            self.logger.error(f"포지션 상태 업데이트 실패 ({symbol}): {e}")
            return False

    async def _handle_partial_fill(self, position: ArbitragePosition):
        """부분 체결 처리"""
        self.logger.warning(f"부분 체결 감지: {position.symbol}")

        try:
            # 체결되지 않은 쪽을 시장가로 체결 시도
            if position.long_filled > 0 and position.short_filled == 0:
                self.logger.info(f"롱 포지션만 체결됨 - 시장가 숏 주문 실행: {position.symbol}")

                short_order = await position.short_exchange.create_order(
                    symbol=position.short_symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    amount=position.quantity,
                    params={'category': 'linear'} if position.short_exchange.name == 'bybit' else {}
                )

                position.short_order_id = short_order.id
                position.short_filled = short_order.filled
                if short_order.average:
                    position.short_entry_price = short_order.average

            elif position.short_filled > 0 and position.long_filled == 0:
                self.logger.info(f"숏 포지션만 체결됨 - 시장가 롱 주문 실행: {position.symbol}")

                long_order = await position.long_exchange.create_order(
                    symbol=position.long_symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    amount=position.quantity,
                    params={'category': 'linear'} if position.long_exchange.name == 'bybit' else {}
                )

                position.long_order_id = long_order.id
                position.long_filled = long_order.filled
                if long_order.average:
                    position.long_entry_price = long_order.average

            # 양쪽 모두 체결됨 확인
            if position.long_filled > 0 and position.short_filled > 0:
                position.status = PositionStatus.OPEN

                if self.notification_manager:
                    await self.notification_manager.send_slack_notification(
                        f"부분 체결 복구 완료: {position.symbol}\n"
                        f"시장가 주문으로 포지션 완성"
                    )

        except Exception as e:
            self.logger.error(f"부분 체결 처리 실패 ({position.symbol}): {e}")

            if self.notification_manager:
                await self.notification_manager.send_slack_notification(
                    f"⚠️ 부분 체결 처리 실패: {position.symbol}\n"
                    f"수동 확인 필요: {e}",
                    level="ERROR"
                )

    async def close_position(self, symbol: str, reason: str = "조건 충족") -> bool:
        """포지션 청산"""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        if position.status != PositionStatus.OPEN:
            self.logger.warning(f"청산 불가능한 포지션 상태: {position.symbol} ({position.status})")
            return False

        try:
            position.status = PositionStatus.CLOSING
            position.exit_timestamp = time.time()

            self.logger.info(f"포지션 청산 시작: {symbol} (사유: {reason})")

            # 시장가로 청산
            tasks = []

            # 롱 포지션 청산 (매도)
            if position.long_filled > 0:
                tasks.append(self._close_long_position(position))

            # 숏 포지션 청산 (매수)
            if position.short_filled > 0:
                tasks.append(self._close_short_position(position))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과 처리
            success = True
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"청산 중 오류: {result}")
                    success = False

            if success:
                position.status = PositionStatus.CLOSED
                self.logger.info(f"포지션 청산 완료: {symbol}")

                if self.notification_manager:
                    await self.notification_manager.send_slack_notification(
                        f"포지션 청산 완료: {symbol}\n"
                        f"사유: {reason}\n"
                        f"예상 수익: {position.pnl:.2f} USDT"
                    )

            return success

        except Exception as e:
            self.logger.error(f"포지션 청산 실패 ({symbol}): {e}")

            if self.notification_manager:
                await self.notification_manager.send_slack_notification(
                    f"⚠️ 포지션 청산 실패: {symbol}\n"
                    f"오류: {e}",
                    level="ERROR"
                )

            return False

    async def _close_long_position(self, position: ArbitragePosition):
        """롱 포지션 청산"""
        order = await position.long_exchange.create_order(
            symbol=position.long_symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=position.long_filled,
            params={'category': 'linear'} if position.long_exchange.name == 'bybit' else {}
        )

        self.logger.info(f"롱 포지션 청산: {position.symbol} - {order.filled}개")

    async def _close_short_position(self, position: ArbitragePosition):
        """숏 포지션 청산"""
        order = await position.short_exchange.create_order(
            symbol=position.short_symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=position.short_filled,
            params={'category': 'linear'} if position.short_exchange.name == 'bybit' else {}
        )

        self.logger.info(f"숏 포지션 청산: {position.symbol} - {order.filled}개")

    async def close_all_positions(self, reason: str = "시스템 종료"):
        """모든 포지션 청산"""
        open_positions = [
            symbol for symbol, pos in self.positions.items()
            if pos.status in [PositionStatus.OPEN, PositionStatus.PENDING]
        ]

        if not open_positions:
            self.logger.info("청산할 포지션이 없습니다")
            return

        self.logger.info(f"전체 포지션 청산 시작: {len(open_positions)}개")

        if self.notification_manager:
            await self.notification_manager.send_slack_notification(
                f"⚠️ 전체 포지션 청산 시작\n"
                f"대상: {', '.join(open_positions)}\n"
                f"사유: {reason}",
                level="WARNING"
            )

        tasks = []
        for symbol in open_positions:
            tasks.append(self.close_position(symbol, reason))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        self.logger.info(f"전체 포지션 청산 완료: {success_count}/{len(open_positions)}개 성공")

    def get_position_summary(self) -> Dict[str, Any]:
        """포지션 요약 정보"""
        total = len(self.positions)
        by_status = {}

        for pos in self.positions.values():
            status = pos.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "총 포지션 수": total,
            "상태별 분포": by_status,
            "최대 포지션 수": self.max_positions,
            "가용 슬롯": max(0, self.max_positions - by_status.get("pending", 0) - by_status.get("open", 0))
        }
