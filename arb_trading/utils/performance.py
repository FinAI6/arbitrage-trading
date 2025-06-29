# arb_trading/utils/performance.py (상세 로깅 추가)
import time
import psutil
import threading
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging


@dataclass
class PerformanceMetrics:
    """성능 메트릭 데이터"""
    # 전체 처리 시간
    fetch_times: deque = field(default_factory=lambda: deque(maxlen=100))
    spread_calc_times: deque = field(default_factory=lambda: deque(maxlen=100))

    # 거래소별 세부 시간
    exchange_fetch_times: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=100)))

    # API 호출 통계
    api_call_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # 프로세스별 리소스 사용량
    process_cpu_usage: deque = field(default_factory=lambda: deque(maxlen=50))
    process_memory_usage: deque = field(default_factory=lambda: deque(maxlen=50))
    process_memory_mb: deque = field(default_factory=lambda: deque(maxlen=50))


@dataclass
class FetchTiming:
    """개별 Fetch 타이밍 정보"""
    exchange: str
    operation: str  # 'tickers', 'volumes', 'symbols'
    duration: float
    timestamp: float
    success: bool
    error_msg: str = ""


class PerformanceMonitor:
    """성능 모니터링 클래스"""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.metrics = PerformanceMetrics()
        self._start_time = time.time()
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._process = None
        self.logger = logging.getLogger(__name__)

        # 상세 로깅용
        self._current_fetch_timings: List[FetchTiming] = []

        if self.enabled:
            try:
                self._process = psutil.Process(os.getpid())
                self.start_process_monitoring()
                self.logger.info("성능 모니터링 시작 (상세 로깅 활성화)")
            except Exception as e:
                self.logger.warning(f"프로세스 모니터링 초기화 실패: {e}")

    def start_process_monitoring(self):
        """프로세스 리소스 모니터링 시작"""

        def monitor():
            while not self._stop_monitoring.is_set():
                try:
                    if self._process and self._process.is_running():
                        cpu_percent = self._process.cpu_percent(interval=0.1)
                        self.metrics.process_cpu_usage.append(cpu_percent)

                        memory_info = self._process.memory_info()
                        memory_mb = memory_info.rss / 1024 / 1024
                        total_memory = psutil.virtual_memory().total
                        memory_percent = (memory_info.rss / total_memory) * 100

                        self.metrics.process_memory_usage.append(memory_percent)
                        self.metrics.process_memory_mb.append(memory_mb)

                    time.sleep(2)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                except Exception:
                    time.sleep(1)

        self._monitoring_thread = threading.Thread(target=monitor, daemon=True)
        self._monitoring_thread.start()

    def stop_monitoring(self):
        """모니터링 중지"""
        self._stop_monitoring.set()
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=2)

    def start_fetch_cycle(self):
        """Fetch 사이클 시작 (타이밍 초기화)"""
        if self.enabled:
            self._current_fetch_timings.clear()

    def record_exchange_fetch(self, exchange: str, operation: str, duration: float,
                              success: bool = True, error_msg: str = ""):
        """거래소별 fetch 시간 기록"""
        if self.enabled:
            # 상세 타이밍 정보 저장
            timing = FetchTiming(
                exchange=exchange,
                operation=operation,
                duration=duration,
                timestamp=time.time(),
                success=success,
                error_msg=error_msg
            )
            self._current_fetch_timings.append(timing)

            # 거래소별 시간 저장
            self.metrics.exchange_fetch_times[exchange].append(duration)

            # 상세 로깅
            status = "✅" if success else "❌"
            self.logger.info(
                f"📊 {status} {exchange.upper()} {operation}: {duration:.3f}초"
                f"{f' (오류: {error_msg})' if error_msg else ''}"
            )

    def record_fetch_time(self, duration: float):
        """전체 데이터 페치 시간 기록"""
        if self.enabled:
            self.metrics.fetch_times.append(duration)

            # 거래소별 상세 로깅
            if self._current_fetch_timings:
                self.logger.info(f"🔄 전체 데이터 페치 완료: {duration:.3f}초")

                # 거래소별 분석
                exchange_summary = defaultdict(list)
                for timing in self._current_fetch_timings:
                    exchange_summary[timing.exchange].append(timing.duration)

                for exchange, durations in exchange_summary.items():
                    total_time = sum(durations)
                    avg_time = total_time / len(durations)
                    self.logger.info(
                        f"  📈 {exchange.upper()}: {total_time:.3f}초 "
                        f"(평균: {avg_time:.3f}초, 호출: {len(durations)}회)"
                    )

    def record_spread_calc_time(self, duration: float, symbols_count: int = 0):
        """스프레드 계산 시간 기록"""
        if self.enabled:
            self.metrics.spread_calc_times.append(duration)

            # 상세 로깅
            if symbols_count > 0:
                per_symbol = duration / symbols_count * 1000  # ms per symbol
                self.logger.info(
                    f"⚡ 스프레드 계산 완료: {duration:.3f}초 "
                    f"({symbols_count}개 심볼, 심볼당 {per_symbol:.1f}ms)"
                )
            else:
                self.logger.info(f"⚡ 스프레드 계산 완료: {duration:.3f}초")

    def record_total_cycle_time(self, total_duration: float, fetch_duration: float,
                                calc_duration: float, symbols_processed: int):
        """전체 사이클 시간 기록 및 상세 로깅"""
        if self.enabled:
            overhead = total_duration - fetch_duration - calc_duration

            self.logger.info("=" * 60)
            self.logger.info(f"🎯 스프레드 모니터링 사이클 완료")
            self.logger.info(f"   전체 시간: {total_duration:.3f}초")
            self.logger.info(f"   ├─ 데이터 페치: {fetch_duration:.3f}초 ({fetch_duration / total_duration * 100:.1f}%)")
            self.logger.info(f"   ├─ 스프레드 계산: {calc_duration:.3f}초 ({calc_duration / total_duration * 100:.1f}%)")
            self.logger.info(f"   └─ 기타 처리: {overhead:.3f}초 ({overhead / total_duration * 100:.1f}%)")
            self.logger.info(f"   처리된 심볼: {symbols_processed}개")

            if symbols_processed > 0:
                throughput = symbols_processed / total_duration
                self.logger.info(f"   처리 성능: {throughput:.1f} 심볼/초")

            self.logger.info("=" * 60)

    def record_api_call(self, exchange: str):
        """API 호출 횟수 기록"""
        if self.enabled:
            self.metrics.api_call_counts[exchange] += 1

    def record_error(self, error_type: str):
        """에러 발생 기록"""
        if self.enabled:
            self.metrics.error_counts[error_type] += 1

    def get_exchange_performance_summary(self) -> Dict[str, Any]:
        """거래소별 성능 요약"""
        if not self.enabled:
            return {}

        summary = {}
        for exchange, times in self.metrics.exchange_fetch_times.items():
            if times:
                summary[exchange] = {
                    "평균 응답시간": f"{sum(times) / len(times):.3f}초",
                    "최근 10회 평균": f"{sum(list(times)[-10:]) / min(10, len(times)):.3f}초",
                    "최소 시간": f"{min(times):.3f}초",
                    "최대 시간": f"{max(times):.3f}초",
                    "총 호출 횟수": len(times)
                }

        return summary

    def get_performance_summary(self) -> Dict[str, Any]:
        """성능 요약 정보 반환"""
        if not self.enabled:
            return {"성능 모니터링": "비활성화됨"}

        summary = {
            # "실행 시간": f"{time.time() - self._start_time:.1f}초",
            "전체 성능": {
                "데이터 페치 평균": f"{sum(self.metrics.fetch_times) / len(self.metrics.fetch_times):.3f}초" if self.metrics.fetch_times else "N/A",
                # "스프레드 계산 평균": f"{sum(self.metrics.spread_calc_times) / len(self.metrics.spread_calc_times):.3f}초" if self.metrics.spread_calc_times else "N/A",
                # "총 사이클 수": len(self.metrics.fetch_times)
            },
            "거래소별 성능": self.get_exchange_performance_summary(),
            # "API 호출 통계": dict(self.metrics.api_call_counts),
            "에러 발생 통계": dict(self.metrics.error_counts)
        }

        # 프로세스 리소스 정보
        if self.metrics.process_cpu_usage and self.metrics.process_memory_mb:
            avg_cpu = sum(self.metrics.process_cpu_usage) / len(self.metrics.process_cpu_usage)
            current_memory = self.metrics.process_memory_mb[-1] if self.metrics.process_memory_mb else 0

            summary["프로세스 리소스"] = {
                "평균 CPU": f"{avg_cpu:.1f}%",
                "현재 메모리": f"{current_memory:.1f} MB"
            }

        return summary
