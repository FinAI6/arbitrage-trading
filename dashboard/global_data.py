from datetime import datetime, timedelta
import streamlit as st

from dashboard.exchanges import BinanceExchange, BybitExchange, BitgetExchange
from dashboard.notifications import send_telegram_alert

# 사용자 설정
spread_threshold = 0.0  # st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
volume_threshold = 500_000  # st.sidebar.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)

spread_list = []
top_spreads = []

if "alert_log" not in st.session_state:
    st.session_state.alert_log = {}

binance = BinanceExchange()
bybit = BybitExchange()
bitget = BitgetExchange()
exchange_dict = {'Binance': binance, 'Bybit': bybit, 'Bitget': bitget}


def update_spreads():
    global spread_list, top_spreads
    binance_symbols = binance.get_symbols()
    binance_prices = binance.get_prices()
    binance_volumes = binance.get_24h_volume()
    binance_funding = binance.get_funding_rates()
    bybit_prices = bybit.get_prices()
    bybit_symbols = bybit.get_symbols()
    bybit_funding = bybit.get_funding_rates()
    common_symbols = [
        s for s in binance_symbols & bybit_symbols
        if s in binance_prices and s in bybit_prices and binance_volumes.get(s, 0) >= volume_threshold
    ]
    for symbol in common_symbols:
        b_price = binance_prices[symbol]
        y_price = bybit_prices[symbol]
        spread = abs(b_price - y_price)
        spread_pct = spread / min(b_price, y_price) * 100
        spread_list.append({
            "symbol": symbol,
            "binance": b_price,
            "bybit": y_price,
            "spread": spread,
            "spread_pct": round(spread_pct, 4),
            "volume": binance_volumes.get(symbol, 0),
            "binance_funding": binance_funding.get(symbol, 0.0),
            "bybit_funding": bybit_funding.get(symbol, 0.0)
        })

    spread_list = sorted(spread_list, key=lambda x: x["spread_pct"], reverse=True)
    top_spreads = spread_list[:12]

    # 이 아래에 알림 조건 루프 삽입
    for item in spread_list:
        symbol = item["symbol"]
        spread_pct = item["spread_pct"]
        binance_funding = item["binance_funding"]
        bybit_funding = item["bybit_funding"]
        funding_gap = abs(binance_funding - bybit_funding)
        now = datetime.now()

        # 스프레드 알림
        if spread_pct >= 0.5:
            last_sent = st.session_state.alert_log.get(f"{symbol}_spread")
            if not last_sent or now - last_sent >= timedelta(hours=1):
                msg = (
                    f"🚨 <b>{symbol} - 스프레드 경고</b>\n"
                    f"💹 스프레드: <b>{spread_pct:.4f}%</b>\n"
                    f"💰 Binance: ${item['binance']:.2f} | Bybit: ${item['bybit']:.2f}"
                )
                send_telegram_alert(msg)
                st.session_state.alert_log[f"{symbol}_spread"] = now

        # 펀딩비 알림 (Binance 또는 Bybit 중 하나라도 크면)
        if binance_funding >= 0.5 or bybit_funding >= 0.5:
            last_sent = st.session_state.alert_log.get(f"{symbol}_funding")
            if not last_sent or now - last_sent >= timedelta(hours=1):
                msg = (
                    f"📢 <b>{symbol} - 펀딩비 경고</b>\n"
                    f"📊 Binance: {binance_funding:.4f}% | Bybit: {bybit_funding:.4f}%"
                )
                send_telegram_alert(msg)
                st.session_state.alert_log[f"{symbol}_funding"] = now

        # 펀딩비 갭 알림
        if funding_gap >= 0.3:
            last_sent = st.session_state.alert_log.get(f"{symbol}_gap")
            if not last_sent or now - last_sent >= timedelta(hours=1):
                msg = (
                    f"⚠️ <b>{symbol} - 펀딩비 차이 경고</b>\n"
                    f"📊 Binance: {binance_funding:.4f}% | Bybit: {bybit_funding:.4f}%\n"
                    f"🔀 차이: <b>{funding_gap:.4f}%</b>"
                )
                send_telegram_alert(msg)
                st.session_state.alert_log[f"{symbol}_gap"] = now
