from collections import defaultdict, deque
from datetime import datetime
from itertools import permutations

import pandas as pd
import streamlit as st
from dashboard.constants import MAX_SPREAD_HISTORY
from dashboard.global_data import exchange_dict


def get_spread_data_name(ex1: str, ex2: str) -> str:
    return f"{ex1}_{ex2}_spread_data"


def update_chart_of_spread_dataframe(df: pd.DataFrame, exchange1_name: str, exchange2_name: str):
    spread_data_name = get_spread_data_name(exchange1_name, exchange2_name)
    if spread_data_name not in st.session_state:
        # 심볼별 spread_pct 저장용 구조
        st.session_state[spread_data_name] = defaultdict(lambda: deque(maxlen=MAX_SPREAD_HISTORY))
    spread_history = st.session_state[spread_data_name]

    spread_history['time'].append(datetime.now().strftime("%H:%M:%S"))

    # 각 symbol에 대해 spread_pct 값 추가
    for symbol, row in df.iterrows():
        spread_pct = row["spread_pct"]
        spread_history[symbol].append(spread_pct)
        df.at[symbol, "chart"] = list(spread_history[symbol])
