from collections import defaultdict

import streamlit as st
from streamlit.column_config import NumberColumn, AreaChartColumn
from streamlit_autorefresh import st_autorefresh

from dashboard.charts import update_chart_of_spread_dataframe
from dashboard.spread import create_spread_dataframe
from dashboard.global_data import exchange_dict

st.set_page_config(
    page_title="Real-time Price List",
    page_icon="💰",
    layout="wide"
)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")
st.markdown("### 💰 실시간 가격 비교")


# Select target exchanges
exchange1_name = st.sidebar.selectbox("1st Exchange", exchange_dict)
exchange2_name = st.sidebar.selectbox("2nd Exchange", {k: v for k, v in exchange_dict.items() if k != exchange1_name})
spread_data_name = f"{exchange1_name}_{exchange2_name}_data"
if spread_data_name not in st.session_state:
    st.session_state[spread_data_name] = defaultdict(list)

# Find common symbols
exchange1 = exchange_dict[exchange1_name]
exchange2 = exchange_dict[exchange2_name]

df = create_spread_dataframe(exchange1, exchange2)
update_chart_of_spread_dataframe(df, exchange1_name, exchange2_name)
df.sort_values(by='spread_pct', ascending=False, inplace=True)
st.dataframe(df,
             column_config={
                 "symbol": "Symbol",
                 "ex1_price": NumberColumn(f"{exchange1_name}가격", format="$%.5g"),
                 "ex2_price": NumberColumn(f"{exchange2_name}가격", format="$%.5g"),
                 "spread": NumberColumn("차이", format="$%.5g"),
                 "spread_pct": NumberColumn("차이율", format="%.2f%%"),
                 "chart": AreaChartColumn("차트", width=100),
                 "ex1_volume": NumberColumn(f"{exchange1_name}거래량", format="%d"),
                 "ex2_volume": NumberColumn(f"{exchange2_name}거래량", format="%d"),
                 "ex1_funding_rate": NumberColumn(f"{exchange1_name}펀딩피(%)", format="%.4g%%"),
                 "ex2_funding_rate": NumberColumn(f"{exchange2_name}펀딩피(%)", format="%.4g%%"),
             },
             height=600)
