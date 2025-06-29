# arb_trading/core/arbitrage_engine.py (종료 처리 수정)
import asyncio
import time
import signal
import sys
from typing import Dict, List, Optional
from collections import defaultdict, deque
from ..exchanges.base import BaseExchange, OrderType, OrderSide, Direction
from ..config.settings import ConfigManager, TradingConfig, OrderConfig, RiskConfig
from .spread_monitor import SpreadMonitor, SpreadData
from .position_manager import PositionManager, ArbitragePosition, PositionStatus
from ..utils.performance import PerformanceMonitor
from ..utils.notifications import NotificationManager
from ..utils.logger import setup_logger
import logging
import traceback


class ArbitrageEngine:
    """차익거래 엔진 메인 클래스"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.logger = setup_logger("arbitrage_engine",
                                   level="INFO",
                                   log_file="logs/arbitrage.log")

        # 설정 로드
        self.trading_config = config_manager.trading
        self.order_config = config_manager.orders
        self.risk_config = config_manager.risk

        # 컴포넌트 초기화
        self.exchanges: Dict[str, BaseExchange] = {}
        self.spread_monitor: Optional[SpreadMonitor] = None
        self.position_manager: Optional[PositionManager] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.notification_manager: Optional[NotificationManager] = None

        # 상태 관리
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self._shutdown_requested = False

        # 스프레드 히스토리 (진입 조건 판단용)
        self.spread_history = defaultdict(lambda: deque(maxlen=self.trading_config.spread_hold_count))
        self.top1_history = defaultdict(lambda: deque(maxlen=self.trading_config.spread_hold_count))
        self.exit_condition_history = defaultdict(lambda: deque(maxlen=self.trading_config.spread_hold_count))

        # 로그 버퍼
        self.log_buffer = []
        self.log_buffer_size = config_manager.monitoring.log_buffer_size

        # 시그널 핸들러 등록
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """시그널 핸들러 설정"""

        def signal_handler(signum, frame):
            self.logger.info(f"종료 신호 수신: {signum}")
            self._shutdown_requested = True
            self.shutdown_event.set()

            # 즉시 종료를 위한 추가 처리
            if not self.is_running:
                sys.exit(0)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            self.logger.debug("시그널 핸들러 등록 성공")
        except Exception as e:
            self.logger.warning(f"시그널 핸들러 등록 실패: {e}")

    async def initialize(self):
        """엔진 초기화"""
        try:
            # 성능 모니터 초기화
            try:
                self.performance_monitor = PerformanceMonitor(
                    enabled=self.config.monitoring.performance_logging
                )
            except Exception as e:
                self.logger.error(f"❌ 성능 모니터 초기화 실패: {e}")
                raise

            # 알림 관리자 초기화
            try:
                notification_config = self.config.notifications
                self.notification_manager = NotificationManager(
                    slack_webhook=notification_config.slack_webhook,
                    telegram_token=notification_config.telegram_token,
                    telegram_chat_id=notification_config.telegram_chat_id,
                    email_config={
                        'smtp_server': notification_config.email_smtp,
                        'user': notification_config.email_user,
                        'password': notification_config.email_password
                    } if notification_config.email_smtp else {}
                )
            except Exception as e:
                self.logger.error(f"❌ 알림 관리자 초기화 실패: {e}")
                raise

            # 거래소 초기화
            try:
                await self._initialize_exchanges()
            except Exception as e:
                self.logger.error(f"❌ 거래소 초기화 실패: {e}")
                raise

            # 스프레드 모니터 초기화
            try:
                self.spread_monitor = SpreadMonitor(
                    exchanges=self.exchanges,
                    min_volume_usdt=self.trading_config.min_volume_usdt,
                    top_symbol_limit=self.trading_config.top_symbol_limit,
                    performance_monitor=self.performance_monitor
                )
            except Exception as e:
                self.logger.error(f"❌ 스프레드 모니터 초기화 실패: {e}")
                raise

            # 포지션 관리자 초기화
            try:
                self.position_manager = PositionManager(
                    max_positions=self.trading_config.max_positions,
                    position_timeout=self.risk_config.position_timeout_seconds,
                    order_timeout=self.risk_config.order_timeout_seconds,
                    notification_manager=self.notification_manager
                )
            except Exception as e:
                self.logger.error(f"❌ 포지션 관리자 초기화 실패: {e}")
                raise

            # self.logger.info("✅ 차익거래 엔진 초기화 완료")

        except Exception as e:
            self.logger.error(f"❌ 엔진 초기화 실패: {e}")
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            raise

    async def _initialize_exchanges(self):
        """거래소 초기화"""
        try:
            from ..exchanges.binance import BinanceExchange
            from ..exchanges.bybit import BybitExchange
        except Exception as e:
            self.logger.error(f"❌ 거래소 모듈 임포트 실패: {e}")
            raise

        exchange_configs = self.config.exchanges
        # self.logger.info(f"설정된 거래소: {list(exchange_configs.keys())}")

        for exchange_name, config in exchange_configs.items():

            if not config.enabled:
                self.logger.info(f"   거래소 '{exchange_name}' 비활성화됨, 건너뜀")
                continue

            try:
                if exchange_name == 'binance':
                    exchange = BinanceExchange(
                        api_key=config.api_key,
                        secret=config.secret
                    )
                elif exchange_name == 'bybit':
                    exchange = BybitExchange(
                        api_key=config.api_key,
                        secret=config.secret
                    )
                else:
                    self.logger.warning(f"지원하지 않는 거래소: {exchange_name}")
                    continue

                # 연결 테스트
                await exchange.connect()

                self.exchanges[exchange_name] = exchange

            except Exception as e:
                self.logger.error(f"❌ '{exchange_name}' 거래소 초기화 실패: {e}")
                self.logger.error(f"상세 오류: {traceback.format_exc()}")
                # 거래소 초기화 실패는 치명적이므로 중단하지 않고 계속 진행

        if len(self.exchanges) < 2:
            error_msg = f"최소 2개의 거래소가 필요합니다 (현재: {len(self.exchanges)}개)"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # self.logger.info(f"✅ 총 {len(self.exchanges)}개 거래소 초기화 완료: {list(self.exchanges.keys())}")

    async def run(self):
        """엔진 실행"""
        try:
            # self.logger.info("✅ 차익거래 엔진 실행 단계 시작...")

            # 초기화
            await self.initialize()
            self.is_running = True
            # self.logger.info("✅ initialize() 완료, is_running = True")

            self.logger.info(f"🔄 차익거래 모니터링 시작 ({self.config.monitoring.fetch_interval}초 간격)")

            # 초기 스프레드 데이터 조회 테스트
            # self.logger.info("📊 초기 스프레드 데이터 조회 테스트 중...")
            try:
                initial_spreads = await self.spread_monitor.fetch_spread_data()
                self.logger.info(f"✅ 초기 스프레드 데이터 조회 성공: {len(initial_spreads)}개 심볼")

            except Exception as e:
                self.logger.error(f"❌ 초기 스프레드 데이터 조회 실패: {e}")
                import traceback
                self.logger.error(f"상세 오류: {traceback.format_exc()}")
                raise

            # 메인 루프 시작
            self.logger.info("🚀 메인 모니터링 루프 시작...")
            loop_count = 0

            while self.is_running and not self.shutdown_event.is_set():
                try:
                    self.logger.debug(f"루프 {loop_count + 1} 시작...")

                    # 종료 요청 확인
                    if self._shutdown_requested:
                        self.logger.info("종료 요청 감지됨")
                        break

                    loop_start_time = time.time()

                    # 스프레드 데이터 조회
                    self.logger.debug("스프레드 데이터 조회 중...")
                    spread_data = await self.spread_monitor.fetch_spread_data()

                    if not spread_data:
                        self.logger.warning("스프레드 데이터를 조회할 수 없습니다")
                        await asyncio.sleep(self.config.monitoring.fetch_interval)
                        continue

                    # 상위 3개 스프레드 표시
                    await self._display_top_spreads(spread_data[:3])

                    # Top1 기록 업데이트
                    self._update_top1_history(spread_data)

                    # 포지션 상태 업데이트
                    await self._update_positions()

                    # 진입 조건 확인
                    await self._check_entry_conditions(spread_data)

                    # 청산 조건 확인
                    await self._check_exit_conditions(spread_data)

                    # 로그 버퍼 플러시
                    loop_count += 1
                    if loop_count % 3 == 0:
                        await self._flush_logs()

                    # 성능 정보 표시
                    if self.performance_monitor and self.performance_monitor.enabled:
                        if loop_count % 10 == 0:  # 10회마다 표시
                            perf_summary = self.performance_monitor.get_performance_summary()
                            self.logger.info(f"📈 성능 정보: {perf_summary}")

                    # 대기 (종료 신호 확인과 함께)
                    loop_duration = time.time() - loop_start_time
                    sleep_time = max(0, self.config.monitoring.fetch_interval - loop_duration)

                    self.logger.debug(f"루프 {loop_count} 완료 (소요: {loop_duration:.3f}초, 대기: {sleep_time:.3f}초)")

                    if sleep_time > 0:
                        try:
                            await asyncio.wait_for(self.shutdown_event.wait(), timeout=sleep_time)
                            self.logger.info("종료 신호를 받아 루프 종료")
                            break  # 종료 신호 받음
                        except asyncio.TimeoutError:
                            pass  # 정상적인 타임아웃, 계속 진행

                except KeyboardInterrupt:
                    self.logger.info("KeyboardInterrupt 감지")
                    break
                except Exception as e:
                    self.logger.error(f"❌ 메인 루프 오류: {e}")
                    import traceback
                    self.logger.error(f"상세 오류: {traceback.format_exc()}")

                    if self.performance_monitor:
                        self.performance_monitor.record_error("main_loop_error")

                    await asyncio.sleep(5)  # 오류 시 5초 대기

            self.logger.info("메인 루프 종료됨")

        except KeyboardInterrupt:
            self.logger.info("사용자 중단 요청")
        except Exception as e:
            self.logger.error(f"❌ 엔진 실행 중 치명적 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            raise
        finally:
            self.logger.info("🛑 엔진 종료 처리 시작...")
            await self.shutdown()

    async def _display_top_spreads(self, top_spreads: List[SpreadData]):
        """상위 스프레드 표시"""
        try:
            if top_spreads:
                spreads_text = " | ".join([
                    f"{item.symbol} ({item.spread_pct:+.2f}%)"
                    for item in top_spreads
                ])
                self.logger.info(f"🔝 Top 3 스프레드: {spreads_text}")
            else:
                self.logger.warning(f"표시할 스프레드 데이터가 없습니다")
        except Exception as e:
            self.logger.error(f"❌ 스프레드 표시 중 오류: {e}")

    def _update_top1_history(self, spread_data: List[SpreadData]):
        """Top1 히스토리 업데이트"""
        try:
            if spread_data:
                top1_symbol = spread_data[0].symbol
                self.top1_history[top1_symbol].append(True)

                # 나머지 심볼들은 False
                for item in spread_data[1:4]:  # 상위 4개 정도만 체크
                    self.top1_history[item.symbol].append(False)
        except Exception as e:
            self.logger.error(f"❌ Top1 히스토리 업데이트 중 오류: {e}")

    async def _update_positions(self):
        """포지션 상태 업데이트"""
        try:
            if not self.position_manager:
                return

            pending_symbols = [
                symbol for symbol, pos in self.position_manager.positions.items()
                if pos.status == PositionStatus.PENDING
            ]

            for symbol in pending_symbols:
                await self.position_manager.update_position_status(symbol)
        except Exception as e:
            self.logger.error(f"❌ 포지션 업데이트 중 오류: {e}")

    async def _check_entry_conditions(self, spread_data: List[SpreadData]):
        """진입 조건 확인"""
        try:
            if not self.position_manager or not self.position_manager.can_open_position():
                return

            # 스프레드 임계값 이상인 항목들만 필터링
            filtered_spreads = [
                item for item in spread_data
                if item.abs_spread_pct >= self.trading_config.spread_threshold
            ]

            if filtered_spreads:
                self.logger.debug(f"임계값 이상 스프레드: {len(filtered_spreads)}개")

            for spread_item in filtered_spreads:
                symbol = spread_item.symbol

                # 이미 포지션이 있는 경우 건너뛰기
                if symbol in self.position_manager.positions:
                    continue

                # 스프레드 히스토리 업데이트
                self.spread_history[symbol].append(spread_item.spread_pct)

                # 진입 조건 확인
                if self._should_enter_position(symbol, spread_item):
                    self.logger.info(f"🟢 조건 충족: {symbol} → 시뮬레이션 진입")
        except Exception as e:
            self.logger.error(f"❌ 진입 조건 확인 중 오류: {e}")

    def _should_enter_position(self, symbol: str, spread_data: SpreadData) -> bool:
        """포지션 진입 조건 확인"""
        try:
            # 스프레드 지속 조건
            spread_hist = self.spread_history[symbol]
            if len(spread_hist) < self.trading_config.spread_hold_count:
                return False

            # 모든 히스토리가 임계값 이상인지 확인
            if not all(abs(s) >= self.trading_config.spread_threshold for s in spread_hist):
                return False

            # Top1 지속 조건
            top1_hist = self.top1_history[symbol]
            if len(top1_hist) < self.trading_config.spread_hold_count:
                return False

            if not all(top1_hist):
                return False

            return True
        except Exception as e:
            self.logger.error(f"❌ 진입 조건 확인 중 오류 ({symbol}): {e}")
            return False

    async def _check_exit_conditions(self, spread_data: List[SpreadData]):
        """청산 조건 확인 (시뮬레이션용)"""
        try:
            # 시뮬레이션에서는 실제 포지션이 없으므로 간단히 처리
            pass
        except Exception as e:
            self.logger.error(f"❌ 청산 조건 확인 중 오류: {e}")

    async def _flush_logs(self):
        """로그 버퍼 플러시"""
        try:
            if self.log_buffer:
                self.log_buffer.clear()
        except Exception as e:
            self.logger.error(f"❌ 로그 플러시 중 오류: {e}")

    async def shutdown(self):
        """시스템 종료"""
        try:
            if not self.is_running:
                return

            self.logger.info("차익거래 시스템 종료 시작...")
            self.is_running = False

            # 모든 포지션 청산 (시뮬레이션에서는 생략)
            if self.position_manager and not self.trading_config.simulation_mode:
                await self.position_manager.close_all_positions("시스템 종료")

            await self.cleanup()
        except Exception as e:
            self.logger.error(f"❌ 시스템 종료 중 오류: {e}")

    async def cleanup(self):
        """리소스 정리"""
        try:
            # 거래소 연결 해제
            cleanup_tasks = []
            for exchange in self.exchanges.values():
                cleanup_tasks.append(exchange.disconnect())

            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

            # 성능 모니터 정리
            if self.performance_monitor:
                self.performance_monitor.stop_monitoring()

            self.logger.info("리소스 정리 완료")

        except Exception as e:
            self.logger.error(f"리소스 정리 중 오류: {e}")


# 디버깅용 최소 테스트 함수 추가
async def test_spread_monitor_only():
    """스프레드 모니터만 단독 테스트"""
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("test")

    try:
        logger.info("1. 거래소 객체 생성...")
        from arb_trading.exchanges.binance import BinanceExchange
        from arb_trading.exchanges.bybit import BybitExchange

        binance = BinanceExchange()
        bybit = BybitExchange()
        exchanges = {"binance": binance, "bybit": bybit}
        logger.info("✅ 거래소 객체 생성 완료")

        logger.info("2. 거래소 연결...")
        await binance.connect()
        await bybit.connect()
        logger.info("✅ 거래소 연결 완료")

        logger.info("3. 스프레드 모니터 생성...")
        from arb_trading.core.spread_monitor import SpreadMonitor
        monitor = SpreadMonitor(exchanges=exchanges)
        logger.info("✅ 스프레드 모니터 생성 완료")

        logger.info("4. 스프레드 데이터 조회...")
        spreads = await monitor.fetch_spread_data()
        logger.info(f"✅ 스프레드 데이터 조회 완료: {len(spreads)}개")

        if spreads:
            logger.info(f"상위 3개: {spreads[:3]}")

        logger.info("5. 연결 해제...")
        await binance.disconnect()
        await bybit.disconnect()
        logger.info("✅ 테스트 완료")

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_spread_monitor_only())
