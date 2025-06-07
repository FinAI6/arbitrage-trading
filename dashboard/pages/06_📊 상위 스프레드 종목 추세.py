from collections import defaultdict

import streamlit as st
import pandas as pd
import plotly.express as px

from dashboard.charts import update_chart_of_spread_dataframe
from dashboard.exchanges import BinanceExchange, BybitExchange
from dashboard.global_data import exchange_dict
from dashboard.spread import create_spread_dataframe

st.set_page_config(
    page_title="Top Spread Trends",
    page_icon="📊",
    layout="wide"
)

st.markdown("### 🔍 스프레드 상위 10개 종목 - 과거 추이 분석 (1분봉 기준)")

duration_hours = st.sidebar.slider("조회 시간 (시간 단위)", 1, 6, 3, key="top_spread_duration")
minutes = duration_hours * 60

# Select target exchanges
row = st.columns(2)
with row[0]:
    exchange1_name = st.selectbox("1st Exchange", exchange_dict)
with row[1]:
    exchange2_name = st.selectbox("2nd Exchange", {k: v for k, v in exchange_dict.items() if k != exchange1_name})
    spread_data_name = f"{exchange1_name}_{exchange2_name}_data"
    if spread_data_name not in st.session_state:
        st.session_state[spread_data_name] = defaultdict(list)

# Find common symbols
exchange1 = exchange_dict[exchange1_name]
exchange2 = exchange_dict[exchange2_name]

df = create_spread_dataframe(exchange1, exchange2)
update_chart_of_spread_dataframe(df, exchange1_name, exchange2_name)

top_symbols = df.index[:10]

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
