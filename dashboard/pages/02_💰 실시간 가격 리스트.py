import streamlit as st
import pandas as pd
import dashboard.global_data as gd
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Real-time Price List",
    page_icon="💰",
    layout="wide"
)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")
st.markdown("### 💵 실시간 가격 비교 (Binance vs Bybit)")
gd.update_spreads()

filtered = [item for item in gd.spread_list if item['spread_pct'] >= gd.spread_threshold]
if not filtered:
    st.info("해당 기준 이상의 종목이 없습니다.")
else:
    price_df = pd.DataFrame(filtered)[[
        "symbol", "binance", "bybit", "spread", "spread_pct", "volume",
        "binance_funding", "bybit_funding"
    ]]
    price_df.columns = [
        "심볼", "Binance 가격", "Bybit 가격", "가격 차이 ($)", "차이율 (%)",
        "거래량 (USDT)", "Binance 펀딩피 (%)", "Bybit 펀딩피 (%)"
    ]
    price_df["🚨 알림"] = price_df["차이율 (%)"].apply(lambda x: "🔔" if x > gd.spread_threshold else "")

    formatted_df = price_df.sort_values("차이율 (%)", ascending=False).copy()
    formatted_df["Binance 가격"] = formatted_df["Binance 가격"].map("${:,.2f}".format)
    formatted_df["Bybit 가격"] = formatted_df["Bybit 가격"].map("${:,.2f}".format)
    formatted_df["가격 차이 ($)"] = formatted_df["가격 차이 ($)"].map("${:,.2f}".format)
    formatted_df["차이율 (%)"] = formatted_df["차이율 (%)"].map("{:.4f}%".format)
    formatted_df["거래량 (USDT)"] = formatted_df["거래량 (USDT)"].map("{:,}".format)
    formatted_df["Binance 펀딩피 (%)"] = formatted_df["Binance 펀딩피 (%)"].map("{:.4f}%".format)
    formatted_df["Bybit 펀딩피 (%)"] = formatted_df["Bybit 펀딩피 (%)"].map("{:.4f}%".format)

    st.write(formatted_df)
