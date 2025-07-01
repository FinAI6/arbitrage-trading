# conftest.py (pytest 설정)
import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """세션 스코프 이벤트 루프"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
