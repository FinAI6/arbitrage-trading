# This file has been deleted as Bitget functionality has been removed
import pandas as pd
import streamlit as st
from dashboard.exchanges import bitget, bybit

st.set_page_config(
    page_title="Bitget vs Bybit",
    page_icon="💵",
    layout="wide"
)
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
volume_threshold = st.sidebar.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)
bybit_prices, bybit_symbols = bybit.get_bybit_prices()
bybit_funding = bybit.get_bybit_funding_rates()

st.markdown("### ⚖️ Bitget vs Bybit 가격 비교")

# Bitget 데이터 로드
bitget_prices, bitget_symbols, bitget_symbol_map = bitget.get_bitget_prices()

# 공통 심볼 도출 (정규화된 기준)
common_symbols_gy = [
    s for s in bitget_symbols & bybit_symbols
    if s in bitget_prices and s in bybit_prices
]

st.info(f"🔄 공통 비교 가능 종목 수: {len(common_symbols_gy)}")

data = []
for symbol in common_symbols_gy:
    g_price = bitget_prices[symbol]
    y_price = bybit_prices[symbol]

    # 0으로 나누기 방지
    if g_price == 0 or y_price == 0:
        continue

    spread = abs(g_price - y_price)
    spread_pct = spread / min(g_price, y_price) * 100

    data.append({
        "symbol": symbol,
        "Bitget 가격": g_price,
        "Bybit 가격": y_price,
        "가격 차이 ($)": spread,
        "차이율 (%)": spread_pct
    })

df = pd.DataFrame(data)

if df.empty or "차이율 (%)" not in df.columns:
    st.warning("📭 비교 가능한 종목이 없습니다.")
else:
    df = df[df["차이율 (%)"] >= spread_threshold]
    df["🚨 알림"] = df["차이율 (%)"].apply(lambda x: "🔔" if x > spread_threshold else "")
    df = df.sort_values("차이율 (%)", ascending=False)
    df["Bitget 가격"] = df["Bitget 가격"].map("${:,.2f}".format)
    df["Bybit 가격"] = df["Bybit 가격"].map("${:,.2f}".format)
    df["가격 차이 ($)"] = df["가격 차이 ($)"].map("${:,.2f}".format)
    df["차이율 (%)"] = df["차이율 (%)"].map("{:.4f}%".format)
    st.write(df)