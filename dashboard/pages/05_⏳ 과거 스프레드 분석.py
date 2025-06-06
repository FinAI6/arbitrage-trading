import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.exchanges import binance, bybit
import dashboard.global_data as gd

st.set_page_config(
    page_title="Historical Spread Analysis",
    page_icon="⏳",
    layout="wide"
)

st.markdown("### ⏳ 과거 1분봉 스프레드 분석 (Binance vs ByBit)")
volume_threshold = st.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)

binance_symbols = binance.get_binance_futures_symbols()
binance_prices = binance.get_binance_prices()
binance_volumes = binance.get_binance_24h_volume()
bybit_prices, bybit_symbols = bybit.get_bybit_prices()
common_symbols = [
    s for s in binance_symbols & bybit_symbols
    if s in binance_prices and s in bybit_prices and binance_volumes.get(s, 0) >= volume_threshold
]

selected_symbol = st.selectbox("심볼 선택", sorted(common_symbols))
duration_hours = st.slider("조회 시간 (시간 단위)", 1, 6, 3)

minutes = duration_hours * 60
binance_df = binance.get_binance_klines(selected_symbol, minutes)
bybit_df = bybit.get_bybit_klines(selected_symbol, minutes)

if not binance_df.empty and not bybit_df.empty:
    df = pd.merge(binance_df, bybit_df, on="index", how="inner")
    df["timestamp"] = pd.to_datetime(df.index, unit="m", origin=pd.Timestamp.now() - pd.Timedelta(minutes=len(df)))
    df["spread_pct"] = abs(df["binance_price"] - df["bybit_price"]) / df[["binance_price", "bybit_price"]].min(
        axis=1) * 100

    st.markdown(f"**{selected_symbol} - 과거 {duration_hours}시간 스프레드 (%)**")
    fig = px.line(df, x="timestamp", y="spread_pct", title="과거 스프레드 추이 (실제 시간 기준)")
    fig.update_layout(
        height=400,
        xaxis_title="시간",
        yaxis_title="스프레드 (%)",
        xaxis=dict(showgrid=True),
        yaxis=dict(showgrid=True),
        margin=dict(l=40, r=20, t=40, b=40)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("📉 데이터를 불러올 수 없습니다.")