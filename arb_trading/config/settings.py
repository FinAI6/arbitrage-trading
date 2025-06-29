# arb_trading/config/settings.py
import json
import os
from typing import Dict, Any
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class TradingConfig:
    simulation_mode: bool
    max_positions: int
    target_usdt: float
    spread_threshold: float
    exit_percent: float
    spread_hold_count: int
    top_symbol_limit: int
    min_volume_usdt: int


@dataclass
class ExchangeConfig:
    enabled: bool
    fetch_only: bool
    api_key: str
    secret: str


@dataclass
class OrderConfig:
    default_type: str
    market_order_enabled: bool
    stop_loss_enabled: bool
    limit_order_slippage: float


@dataclass
class MonitoringConfig:
    performance_logging: bool
    fetch_interval: int
    log_buffer_size: int


@dataclass
class NotificationConfig:
    slack_webhook: str
    telegram_token: str
    telegram_chat_id: str
    email_smtp: str
    email_user: str
    email_password: str


@dataclass
class RiskConfig:
    max_loss_percent: float
    position_timeout_seconds: int
    order_timeout_seconds: int


class ConfigManager:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._get_default_config_path()
        self._config = self._load_config()

    def _get_default_config_path(self) -> str:
        return str(Path(__file__).parent / "default_config.json")

    def _load_config(self) -> Dict[str, Any]:
        load_dotenv()
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 환경변수에서 API 키 덮어쓰기
            if 'BINANCE_API_KEY' in os.environ:
                config['exchanges']['binance']['api_key'] = os.environ['BINANCE_API_KEY']
            if 'BINANCE_SECRET' in os.environ:
                config['exchanges']['binance']['secret'] = os.environ['BINANCE_SECRET']
            if 'BYBIT_API_KEY' in os.environ:
                config['exchanges']['bybit']['api_key'] = os.environ['BYBIT_API_KEY']
            if 'BYBIT_SECRET' in os.environ:
                config['exchanges']['bybit']['secret'] = os.environ['BYBIT_SECRET']

            return config
        except Exception as e:
            raise Exception(f"설정 파일 로드 실패: {e}")

    @property
    def trading(self) -> TradingConfig:
        return TradingConfig(**self._config['trading'])

    @property
    def exchanges(self) -> Dict[str, ExchangeConfig]:
        return {
            name: ExchangeConfig(**config)
            for name, config in self._config['exchanges'].items()
        }

    @property
    def orders(self) -> OrderConfig:
        return OrderConfig(**self._config['orders'])

    @property
    def monitoring(self) -> MonitoringConfig:
        return MonitoringConfig(**self._config['monitoring'])

    @property
    def notifications(self) -> NotificationConfig:
        return NotificationConfig(**self._config['notifications'])

    @property
    def risk(self) -> RiskConfig:
        return RiskConfig(**self._config['risk_management'])

    def update_config(self, section: str, key: str, value: Any):
        """설정 값 동적 업데이트"""
        if section in self._config and key in self._config[section]:
            self._config[section][key] = value

    def save_config(self, path: str = None):
        """설정을 파일로 저장"""
        save_path = path or self.config_path
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=4, ensure_ascii=False)
