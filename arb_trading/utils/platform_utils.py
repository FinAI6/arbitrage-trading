# arb_trading/utils/platform_utils.py
import asyncio
import sys
import platform
import logging


def setup_windows_event_loop():
    """Windows 환경에서 이벤트 루프 설정"""
    if platform.system() == 'Windows':
        # Windows에서 SelectorEventLoop 사용
        if sys.version_info >= (3, 8):
            # Python 3.8+에서는 ProactorEventLoop가 기본이므로 SelectorEventLoop로 변경
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        else:
            # Python 3.7 이하에서는 SelectorEventLoop가 기본
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)


def get_optimal_connector():
    """플랫폼에 최적화된 aiohttp 커넥터 반환"""
    import aiohttp

    if platform.system() == 'Windows':
        # Windows에서는 기본 커넥터 사용 (DNS 해상도 문제 방지)
        return aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True
        )
    else:
        # Linux/Mac에서는 성능 최적화된 커넥터
        try:
            import aiohttp_speedups  # 선택적 성능 향상
            return aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                ttl_dns_cache=300,
                use_dns_cache=True,
                enable_cleanup_closed=True
            )
        except ImportError:
            return aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
                enable_cleanup_closed=True
            )
