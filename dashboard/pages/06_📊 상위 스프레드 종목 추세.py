import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.exchanges import BinanceExchange, BybitExchange
import dashboard.global_data as gd

st.set_page_config(
    page_title="Top Spread Trends",
    page_icon="📊",
    layout="wide"
)

st.markdown("### 🔍 스프레드 상위 10개 종목 - 과거 추이 분석 (1분봉 기준, Binance vs ByBit)")
duration_hours = st.slider("조회 시간 (시간 단위)", 1, 6, 3, key="top_spread_duration")
minutes = duration_hours * 60

gd.update_spreads()
top_symbols = [item["symbol"] for item in gd.top_spreads[:10]]

binance = BinanceExchange()
bybit = BybitExchange()
for symbol in top_symbols:
    binance_df = binance.get_klines(symbol, minutes)
    bybit_df = bybit.get_klines(symbol, minutes)

    if not binance_df.empty and not bybit_df.empty:
        df = pd.merge(binance_df, bybit_df, on="index", how="inner")
        df["timestamp"] = pd.to_datetime(df.index, unit="m",
                                         origin=pd.Timestamp.now() - pd.Timedelta(minutes=len(df)))
        df["spread_pct"] = abs(df["binance_price"] - df["bybit_price"]) / df[["binance_price", "bybit_price"]].min(
            axis=1) * 100

        st.markdown(f"#### 📌 {symbol}")
        fig = px.line(df, x="timestamp", y="spread_pct", title=f"{symbol} - 스프레드 추이")
        fig.update_layout(
            height=350,
            xaxis_title="시간",
            yaxis_title="스프레드 (%)",
            xaxis=dict(showgrid=True),
            yaxis=dict(showgrid=True),
            margin=dict(l=40, r=20, t=40, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"⚠️ {symbol} - 데이터를 불러올 수 없습니다.")
