from datetime import datetime

import streamlit as st
from streamlit.column_config import Column, NumberColumn, LineChartColumn
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.express as px
import dashboard.global_data as gd

st.set_page_config(
    page_title="스프레드 차트",
    page_icon="📈",
    layout="wide"
)

st.title("📈 스프레드 차트")

if "chart_data" not in st.session_state:
    st.session_state.chart_data = {}

# 사용자 설정
st.sidebar.header("Settings")
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")
gd.update_spreads()

now = datetime.now().strftime("%H:%M:%S")
for i in range(0, len(gd.top_spreads), 3):
    row = st.columns(3)
    for j in range(3):
        if i + j < len(gd.top_spreads):
            data = gd.top_spreads[i + j]
            symbol = data['symbol']
            binance_price = data['binance']
            bybit_price = data['bybit']
            spread = data['spread']
            spread_pct = data['spread_pct']

            if symbol not in st.session_state.chart_data:
                st.session_state.chart_data[symbol] = pd.DataFrame(columns=["Time", "Spread (%)"])
            df = st.session_state.chart_data[symbol]
            df.loc[len(df)] = [now, spread_pct]
            if len(df) > 60:
                df = df.iloc[-60:]
            st.session_state.chart_data[symbol] = df

            with row[j]:
                st.markdown(f"### <span style='font-size:18px'>{symbol}</span>", unsafe_allow_html=True)
                st.markdown(
                    f"<div style='font-size:14px'>"
                    f"Binance: ${binance_price:.2f}<br>Bybit: ${bybit_price:.2f}<br>"
                    f"차이: ${spread:,.2f}<br>차이율: {spread_pct:.4f}%"
                    f"</div>", unsafe_allow_html=True)

                fig = px.line(df, x="Time", y="Spread (%)")
                spread_min = df["Spread (%)"].min()
                spread_max = df["Spread (%)"].max()
                y_min = max(0, spread_min - (spread_max - spread_min) * 0.2)
                y_max = spread_max + (spread_max - spread_min) * 0.2
                fig.update_layout(height=250, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
                fig.update_yaxes(range=[y_min, y_max])
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{symbol}")

                if spread_pct > spread_threshold:
                    st.error(f"🚨 {symbol} 스프레드 {spread_pct:.4f}% 초과!")
