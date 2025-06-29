# arb_trading/utils/logger.py
import logging
import logging.handlers
from pathlib import Path
from typing import Optional
import sys


class ColoredFormatter(logging.Formatter):
    """컬러 로그 포맷터"""

    COLORS = {
        'DEBUG': '\033[36m',  # 청록색
        'INFO': '\033[32m',  # 녹색
        'WARNING': '\033[33m',  # 노랑색
        'ERROR': '\033[31m',  # 빨간색
        'CRITICAL': '\033[35m',  # 자주색
        'RESET': '\033[0m'  # 리셋
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logger(name: str = "arb_trading",
                 log_file: Optional[str] = None,
                 level: str = "INFO",
                 enable_console: bool = True) -> logging.Logger:
    """로거 설정"""

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    colored_formatter = ColoredFormatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(colored_formatter)
        logger.addHandler(console_handler)

    # 파일 핸들러
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 로테이팅 파일 핸들러 (최대 10MB, 5개 파일)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
