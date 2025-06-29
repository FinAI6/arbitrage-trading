# arb_trading/utils/api_helpers.py (새 파일)
"""API 응답 처리 도우미 함수들"""

import logging
from typing import Any, Union, Optional

logger = logging.getLogger(__name__)


def safe_float(value: Any, default: float = 0.0, field_name: str = "unknown") -> float:
    """안전한 float 변환"""
    if value is None or value == '' or value == '0':
        return default

    try:
        result = float(value)
        if result < 0 and default >= 0:
            logger.warning(f"음수 값 감지 ({field_name}): {value}, 기본값 {default} 사용")
            return default
        return result
    except (ValueError, TypeError) as e:
        logger.warning(f"float 변환 실패 ({field_name}): {value} -> {e}, 기본값 {default} 사용")
        return default


def safe_int(value: Any, default: int = 0, field_name: str = "unknown") -> int:
    """안전한 int 변환"""
    if value is None or value == '':
        return default

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"int 변환 실패 ({field_name}): {value} -> {e}, 기본값 {default} 사용")
        return default


def safe_string(value: Any, default: str = "", field_name: str = "unknown") -> str:
    """안전한 string 변환"""
    if value is None:
        return default

    try:
        return str(value).strip()
    except Exception as e:
        logger.warning(f"string 변환 실패 ({field_name}): {value} -> {e}, 기본값 '{default}' 사용")
        return default


def validate_ticker_data(data: dict, symbol: str) -> bool:
    """티커 데이터 유효성 검사"""
    required_fields = ['lastPrice']

    for field in required_fields:
        if field not in data:
            logger.warning(f"필수 필드 누락 ({symbol}): {field}")
            return False

        if data[field] is None or data[field] == '':
            logger.warning(f"필수 필드 비어있음 ({symbol}): {field}")
            return False

    # 가격이 0보다 큰지 확인
    try:
        price = float(data['lastPrice'])
        if price <= 0:
            logger.warning(f"유효하지 않은 가격 ({symbol}): {price}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"가격 파싱 실패 ({symbol}): {data['lastPrice']}")
        return False

    return True


def filter_valid_symbols(tickers_data: list, exchange_name: str) -> list:
    """유효한 심볼만 필터링"""
    valid_tickers = []

    for item in tickers_data:
        symbol = item.get('symbol', '')
        if not symbol:
            continue

        if validate_ticker_data(item, symbol):
            valid_tickers.append(item)
        else:
            logger.debug(f"{exchange_name} 유효하지 않은 티커 제외: {symbol}")

    logger.info(f"{exchange_name} 유효한 티커: {len(valid_tickers)}개 (전체: {len(tickers_data)}개)")
    return valid_tickers
