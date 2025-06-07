from collections import defaultdict
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.express as px
from dashboard.global_data import exchange_dict
from dashboard.charts import update_chart_of_spread_dataframe, get_spread_data_name
from dashboard.spread import create_spread_dataframe

st.set_page_config(
    page_title="스프레드 차트",
    page_icon="📈",
    layout="wide"
)

st.title("📈 스프레드 차트")

# Select target exchanges
exchange1_name = st.sidebar.selectbox("1st Exchange", exchange_dict)
exchange2_name = st.sidebar.selectbox("2nd Exchange", {k: v for k, v in exchange_dict.items() if k != exchange1_name})
spread_data_name = f"{exchange1_name}_{exchange2_name}_data"
if spread_data_name not in st.session_state:
    st.session_state[spread_data_name] = defaultdict(list)


# 사용자 설정
st.sidebar.header("Settings")
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")

df_total = create_spread_dataframe(exchange_dict[exchange1_name],
                             exchange_dict[exchange2_name])
update_chart_of_spread_dataframe(df_total, exchange1_name, exchange2_name)
df_total.sort_values(by='spread_pct', ascending=False, inplace=True)
spread_data_name = get_spread_data_name(exchange1_name, exchange2_name)
timeline = st.session_state[spread_data_name]['time']

top_spreads = df_total.index[:12]
now = datetime.now().strftime("%H:%M:%S")
for i in range(0, len(top_spreads), 3):
    row = st.columns(3)
    for j in range(3):
        if i + j >= len(top_spreads):
            break
        symbol = df_total.index[i + j]
        if not isinstance(symbol, str):
            continue
        # st.write(df.index)
        binance_price = df_total.loc[symbol, 'ex1_price']
        bybit_price = df_total.loc[symbol, 'ex2_price']
        spread = df_total.loc[symbol, 'spread']
        spread_pct = df_total.loc[symbol, 'spread_pct']

        df = pd.DataFrame({"Time": timeline, "Spread (%)": df_total.loc[symbol, 'chart']})
        df.loc[len(df)] = [now, spread_pct]
        if len(df) > 60:
            df = df.iloc[-60:]

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
