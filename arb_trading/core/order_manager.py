# arb_trading/core/order_manager.py
import asyncio
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from ..exchanges.base import BaseExchange, Order, OrderType, OrderSide
import logging


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ManagedOrder:
    """관리되는 주문"""
    order: Order
    exchange: BaseExchange
    created_at: float
    timeout: int = 60
    status: OrderStatus = OrderStatus.PENDING


class OrderManager:
    """주문 관리 클래스"""

    def __init__(self, default_timeout: int = 60):
        self.default_timeout = default_timeout
        self.managed_orders: Dict[str, ManagedOrder] = {}
        self.logger = logging.getLogger(__name__)

    def add_order(self, order: Order, exchange: BaseExchange, timeout: Optional[int] = None) -> str:
        """주문 추가"""
        managed_order = ManagedOrder(
            order=order,
            exchange=exchange,
            created_at=time.time(),
            timeout=timeout or self.default_timeout
        )

        order_key = f"{exchange.name}_{order.id}"
        self.managed_orders[order_key] = managed_order

        self.logger.info(f"주문 관리 시작: {order_key}")
        return order_key

    async def check_order_status(self, order_key: str) -> OrderStatus:
        """주문 상태 확인"""
        if order_key not in self.managed_orders:
            return OrderStatus.CANCELLED

        managed_order = self.managed_orders[order_key]

        try:
            # 타임아웃 체크
            if time.time() - managed_order.created_at > managed_order.timeout:
                await self._handle_timeout_order(order_key, managed_order)
                return OrderStatus.TIMEOUT

            # 주문 상태 조회
            updated_order = await managed_order.exchange.fetch_order(
                managed_order.order.id,
                managed_order.order.symbol
            )

            managed_order.order = updated_order

            if updated_order.filled > 0:
                managed_order.status = OrderStatus.FILLED
                self.logger.info(f"주문 체결 완료: {order_key} - {updated_order.filled}")
                return OrderStatus.FILLED

            return OrderStatus.PENDING

        except Exception as e:
            self.logger.error(f"주문 상태 확인 실패 ({order_key}): {e}")
            return OrderStatus.PENDING

    async def _handle_timeout_order(self, order_key: str, managed_order: ManagedOrder):
        """타임아웃된 주문 처리"""
        self.logger.warning(f"주문 타임아웃: {order_key}")

        try:
            # 주문 취소 시도
            await managed_order.exchange.cancel_order(
                managed_order.order.id,
                managed_order.order.symbol
            )

            managed_order.status = OrderStatus.TIMEOUT
            self.logger.info(f"타임아웃된 주문 취소 완료: {order_key}")

        except Exception as e:
            self.logger.error(f"타임아웃된 주문 취소 실패 ({order_key}): {e}")

    async def cancel_order(self, order_key: str) -> bool:
        """주문 취소"""
        if order_key not in self.managed_orders:
            return False

        managed_order = self.managed_orders[order_key]

        try:
            await managed_order.exchange.cancel_order(
                managed_order.order.id,
                managed_order.order.symbol
            )

            managed_order.status = OrderStatus.CANCELLED
            self.logger.info(f"주문 취소 완료: {order_key}")
            return True

        except Exception as e:
            self.logger.error(f"주문 취소 실패 ({order_key}): {e}")
            return False

    def get_order(self, order_key: str) -> Optional[Order]:
        """주문 정보 조회"""
        if order_key in self.managed_orders:
            return self.managed_orders[order_key].order
        return None

    def remove_order(self, order_key: str):
        """주문 제거"""
        if order_key in self.managed_orders:
            del self.managed_orders[order_key]
            self.logger.info(f"주문 관리 종료: {order_key}")

    async def cleanup_completed_orders(self):
        """완료된 주문들 정리"""
        completed_keys = [
            key for key, managed_order in self.managed_orders.items()
            if managed_order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.TIMEOUT]
        ]

        for key in completed_keys:
            self.remove_order(key)

        if completed_keys:
            self.logger.info(f"완료된 주문 {len(completed_keys)}개 정리 완료")
