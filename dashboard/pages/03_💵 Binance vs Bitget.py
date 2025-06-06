import pandas as pd
import streamlit as st
import dashboard.global_data as gd
from dashboard.exchanges import binance, bitget

st.set_page_config(
    page_title="Binance vs Bitget",
    page_icon="💵",
    layout="wide"
)
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
volume_threshold = st.sidebar.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)
binance_symbols = binance.get_binance_futures_symbols()
binance_prices = binance.get_binance_prices()
binance_volumes = binance.get_binance_24h_volume()
binance_funding = binance.get_binance_funding_rates()
bitget_prices, bitget_symbols, bitget_symbol_map = bitget.get_bitget_prices()

st.markdown("### ⚖️ Binance vs Bitget 가격 비교")
common_symbols_bb = [
    s for s in binance_symbols & bitget_symbols
    if s in binance_prices and s in bitget_prices and binance_volumes.get(s, 0) >= volume_threshold
]

data = []
for symbol in common_symbols_bb:
    b_price = binance_prices[symbol]
    g_price = bitget_prices[symbol]

    # 0으로 나누기 방지
    if b_price == 0 or g_price == 0:
        continue

    spread = abs(b_price - g_price)
    spread_pct = spread / min(b_price, g_price) * 100

    data.append({
        "symbol": symbol,
        "Binance 가격": b_price,
        "Bitget 가격": g_price,
        "가격 차이 ($)": spread,
        "차이율 (%)": spread_pct,
        "거래량 (USDT)": binance_volumes.get(symbol, 0)
    })

df = pd.DataFrame(data)
df = df[df["차이율 (%)"] >= spread_threshold]

if df.empty:
    st.info("해당 기준 이상의 종목이 없습니다.")
else:
    df["🚨 알림"] = df["차이율 (%)"].apply(lambda x: "🔔" if x > gd.spread_threshold else "")
    df = df.sort_values("차이율 (%)", ascending=False)
    df["Binance 가격"] = df["Binance 가격"].map("${:,.2f}".format)
    df["Bitget 가격"] = df["Bitget 가격"].map("${:,.2f}".format)
    df["가격 차이 ($)"] = df["가격 차이 ($)"].map("${:,.2f}".format)
    df["차이율 (%)"] = df["차이율 (%)"].map("{:.4f}%".format)
    df["거래량 (USDT)"] = df["거래량 (USDT)"].map("{:,}".format)
    st.write(df)