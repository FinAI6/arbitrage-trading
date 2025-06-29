# arb_trading/__init__.py (업데이트)
"""
차익거래 시스템

모듈화된 암호화폐 차익거래 자동화 시스템
- 바이낸스, 바이빗 거래소 지원
- 실시간 스프레드 모니터링
- 자동 포지션 관리
- 성능 모니터링 및 알림 시스템

사용법:
    python -m arb_trading                    # 기본 실행
    python -m arb_trading --simulation       # 시뮬레이션 모드
    python -m arb_trading --help            # 도움말
"""

__version__ = "1.0.0"
__author__ = "Arbitrage Team"

from .config.settings import ConfigManager
from .core.arbitrage_engine import ArbitrageEngine
from .core.spread_monitor import SpreadMonitor
from .core.position_manager import PositionManager
from .exchanges.binance import BinanceExchange
from .exchanges.bybit import BybitExchange

__all__ = [
    'ConfigManager',
    'ArbitrageEngine',
    'SpreadMonitor',
    'PositionManager',
    'BinanceExchange',
    'BybitExchange'
]


# 설정 파일 템플릿 생성 함수
def create_config_template(path: str = "config.json"):
    """설정 파일 템플릿 생성"""
    import json
    from pathlib import Path

    template = {
        "trading": {
            "simulation_mode": True,
            "max_positions": 3,
            "target_usdt": 100,
            "spread_threshold": 0.5,
            "exit_percent": 0.5,
            "spread_hold_count": 3,
            "top_symbol_limit": 300,
            "min_volume_usdt": 5000000
        },
        "exchanges": {
            "binance": {
                "enabled": True,
                "fetch_only": False,
                "api_key": "YOUR_BINANCE_API_KEY",
                "secret": "YOUR_BINANCE_SECRET"
            },
            "bybit": {
                "enabled": True,
                "fetch_only": True,
                "api_key": "YOUR_BYBIT_API_KEY",
                "secret": "YOUR_BYBIT_SECRET"
            }
        },
        "orders": {
            "default_type": "limit",
            "market_order_enabled": False,
            "stop_loss_enabled": False,
            "limit_order_slippage": 0.001
        },
        "monitoring": {
            "performance_logging": False,
            "fetch_interval": 5,
            "log_buffer_size": 100
        },
        "notifications": {
            "slack_webhook": "",
            "telegram_token": "",
            "telegram_chat_id": "",
            "email_smtp": "",
            "email_user": "",
            "email_password": ""
        },
        "risk_management": {
            "max_loss_percent": -10,
            "position_timeout_seconds": 300,
            "order_timeout_seconds": 60
        }
    }

    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=4, ensure_ascii=False)

    print(f"✅ 설정 파일 템플릿 생성: {path}")
    print(f"📝 API 키를 입력하고 설정을 수정한 후 사용하세요.")
    print(f"🚀 실행: python -m arb_trading --config {path}")


# 빠른 시작 가이드 표시 함수
def show_quick_start():
    """빠른 시작 가이드 표시"""
    print("""
🚀 차익거래 시스템 빠른 시작 가이드

1️⃣ 설정 파일 생성:
   python -m arb_trading --create-config my_config.json

2️⃣ API 키 설정:
   my_config.json 파일을 열어서 API 키 입력

3️⃣ 시뮬레이션 실행:
   python -m arb_trading --config my_config.json --simulation

4️⃣ 성능 모니터링:
   python -m arb_trading --simulation --performance

5️⃣ 실거래 (주의!):
   python -m arb_trading --config my_config.json

📚 도움말: python -m arb_trading --help
🐛 디버그: python -m arb_trading --simulation --log-level DEBUG
""")


# 사용 예시 및 도움말
USAGE_EXAMPLES = """
📖 사용 예시:

기본 사용법:
  python -m arb_trading                                 # 기본 설정으로 실행
  python -m arb_trading --simulation                    # 시뮬레이션 모드
  python -m arb_trading --help                         # 도움말 표시

설정 관리:
  python -m arb_trading --create-config config.json    # 설정 파일 생성
  python -m arb_trading --config my_config.json        # 커스텀 설정 사용

성능 및 디버깅:
  python -m arb_trading --performance                   # 성능 모니터링
  python -m arb_trading --log-level DEBUG              # 디버그 로그
  python -m arb_trading --performance --log-level DEBUG # 상세 모니터링

파라미터 조정:
  python -m arb_trading --spread-threshold 0.3         # 스프레드 임계값 0.3%
  python -m arb_trading --max-positions 5              # 최대 5개 포지션
  python -m arb_trading --fetch-interval 3             # 3초 간격 조회

조합 사용:
  python -m arb_trading \\
    --config my_config.json \\
    --simulation \\
    --performance \\
    --spread-threshold 0.2 \\
    --log-level INFO
"""
