# 암호화폐 거래소 간 스프레드 모니터링 대시보드

이 프로젝트는 Binance, Bybit, Bitget 등 주요 암호화폐 거래소 간의 가격 차이(스프레드)를 실시간으로 모니터링하고 분석하는 대시보드입니다.

## 거래소 API 문서

- [Binance API 문서](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/)
- [Bybit API 문서](https://bybit-exchange.github.io/docs/)
- [Bitget API 문서](https://www.bitget.com/api-doc/)

## 주요 기능

### 📈 스프레드 차트
- 실시간 스프레드 모니터링
- 다양한 시간대 분석 (1분, 5분, 15분, 30분, 1시간, 4시간, 1일)
- 스프레드 알림 설정

### 💰 실시간 가격 리스트
- 현재 거래소별 가격 비교
- 실시간 스프레드 퍼센트 표시
- 거래소 간 가격 차이 시각화

### 💵 거래소 간 가격 비교
- Binance vs Bitget 가격 비교
- Bitget vs Bybit 가격 비교
- 실시간 가격 차트

### ⏳ 과거 스프레드 분석
- 과거 데이터 기반 스프레드 분석
- 다양한 기간 선택 (1일, 7일, 30일, 90일)
- 장기 트렌드 분석

### 📊 상위 스프레드 종목 추세
- 여러 종목의 스프레드 비교
- 상위 N개 종목 표시
- 실시간 스프레드 순위

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/finai6/arbitrage-trading.git
cd arbitrage-trading
```

2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 의존성 설치
```bash
# pip를 최신 버전으로 업그레이드
pip install --upgrade pip

# 프로젝트 설치
pip install -e .

# 개발 도구 설치 (선택사항)
pip install -e ".[dev]"
```

4. 환경 변수 설정
`.env` 파일을 생성하고 다음 내용을 추가:
```
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
BITGET_API_KEY=your_bitget_api_key
BITGET_API_SECRET=your_bitget_api_secret
```

5. Telegram 알림 설정
`.streamlit/secrets.toml` 파일을 생성하고 다음 내용을 추가:
```toml
[telegram]
bot_token = "your_telegram_bot_token"
chat_id = "your_telegram_chat_id"
```

> **Telegram 봇 생성 방법**
> 1. 텔레그램 앱에서 @BotFather 검색
> 2. `/newbot` 명령어를 보내 새 봇 생성 시작
> 3. 봇의 이름을 입력 (예: "My Arbitrage Bot")
> 4. 봇의 사용자명을 입력 (예: "my_arbitrage_bot")
> 5. BotFather가 봇 토큰을 제공합니다. 이 토큰을 `bot_token`에 사용하세요

> **chat_id 설정 방법**
> 1. 텔레그램 앱에서 @userinfobot 검색
> 2. 봇을 시작하고 아무 메시지나 보내기
> 3. 봇이 당신의 User ID (chat_id)를 알려줍니다

## 실행 방법

1. 대시보드 실행:
```bash
streamlit run dashboard/🏠 Home.py
```

2. 개발 서버 실행 (자동 리로드):
```bash
streamlit run dashboard/🏠 Home.py --server.runOnSave=true
```

## 프로젝트 구조

```
arbitrage-trading/
├── dashboard/                 # Streamlit 대시보드 애플리케이션
│   ├── pages/                # 대시보드 페이지
│   │   ├── 01_📈 스프레드 차트.py
│   │   ├── 02_💰 실시간 가격 비교.py
│   │   ├── 05_⏳ 과거 스프레드 분석.py
│   │   ├── 06_📊 상위 스프레드 종목 추세.py
│   │   └── __init__.py
│   ├── exchanges.py          # 거래소 API 연동
│   ├── charts.py            # 차트 생성 유틸리티
│   ├── notifications.py     # 알림 시스템
│   └── main.py             # 메인 애플리케이션
├── trading/                 # 거래 로직
│   └── arbitrage.py        # 차익거래 로직
├── .streamlit/             # Streamlit 설정
├── pyproject.toml          # 프로젝트 설정 및 의존성
└── README.md              # 프로젝트 문서
```

## 기술 스택

- Python 3.10+
- Streamlit 1.32.0+
- Pandas 2.2.0+
- Plotly 5.18.0+
- CCXT 4.2.15+
- Python-dotenv 1.0.0+
- Python-telegram-bot 20.7+

### 개발 도구
- pytest 7.4.0+ (테스트)
- black 23.7.0+ (코드 포맷팅)
- isort 5.12.0+ (import 정렬)
- mypy 1.5.1+ (타입 체크)
- ruff 0.1.6+ (린터)

## 주의사항

- API 키는 반드시 안전하게 보관하세요.
- 실제 거래에 사용하기 전에 충분한 테스트를 진행하세요.
- 거래소의 API 사용 제한을 확인하고 준수하세요.
- 개발 시에는 black, isort, mypy, ruff를 사용하여 코드 품질을 유지하세요.

## 라이선스

MIT License
