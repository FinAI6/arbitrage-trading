# 차익거래 시스템 (Arbitrage Trading System)

모듈화된 암호화폐 차익거래 자동화 시스템입니다.

## 주요 특징

- 🚀 **고성능**: 비동기 처리로 빠른 데이터 수집 및 거래 실행
- 🔧 **모듈화**: 확장 가능한 구조로 새로운 거래소 쉽게 추가
- 📊 **실시간 모니터링**: 스프레드 실시간 추적 및 성능 측정
- 🛡️ **리스크 관리**: 포지션 크기 제한, 손절 기능
- 📱 **알림 시스템**: Slack, Telegram, Email 지원
- 🎯 **시뮬레이션**: 실거래 전 테스트 가능

## 설치 방법

```bash
# 저장소 클론
git clone https://github.com/yourusername/arb-trading.git
cd arb-trading

# 의존성 설치
pip install -r requirements.txt

# 개발 모드 설치
pip install -e .
```

## 사용법

### 1. 설정 파일 생성

```bash
python -c "from arb_trading import create_config_template; create_config_template('my_config.json')"
```

### 2. API 키 설정

생성된 설정 파일에서 API 키를 입력하세요:

```json
{
  "exchanges": {
    "binance": {
      "api_key": "YOUR_BINANCE_API_KEY",
      "secret": "YOUR_BINANCE_SECRET"
    },
    "bybit": {
      "api_key": "YOUR_BYBIT_API_KEY",
      "secret": "YOUR_BYBIT_SECRET"
    }
  }
}
```

### 3. 실행

```bash
# 시뮬레이션 모드
arb-trading --simulation --config my_config.json

# 실거래 모드 (주의!)
arb-trading --config my_config.json

# 성능 모니터링 활성화
arb-trading --simulation --performance

# 스프레드 임계값 설정
arb-trading --simulation --spread-threshold 0.8
```

## 명령행 옵션

- `--config, -c`: 설정 파일 경로
- `--simulation, -s`: 시뮬레이션 모드
- `--performance, -p`: 성능 모니터링 활성화
- `--log-level, -l`: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `--order-type`: 주문 타입 (limit, market)
- `--max-positions`: 최대 포지션 수
- `--spread-threshold`: 스프레드 임계값 (%)

## 프로젝트 구조

```
arb_trading/
├── config/          # 설정 관리
├── exchanges/       # 거래소 인터페이스
├── core/           # 핵심 로직
├── utils/          # 유틸리티
└── tests/          # 테스트
```

## 라이센스

MIT License