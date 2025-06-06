from collections import defaultdict

import streamlit as st
from streamlit.column_config import Column, NumberColumn, LineChartColumn
import pandas as pd
import dashboard.global_data as gd
from streamlit_autorefresh import st_autorefresh
from dashboard.exchanges import BaseExchange, BinanceExchange, BitgetExchange, BybitExchange

st.set_page_config(
    page_title="Real-time Price List",
    page_icon="💰",
    layout="wide"
)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")
st.markdown("### 💰 실시간 가격 비교 (Binance vs Bybit)")

exchange_dict = {'Binance': BinanceExchange(),
                 'Bybit': BybitExchange(),
                 'Bitget': BitgetExchange()}

# Select target exchanges
row = st.columns(2)
with row[0]:
    exchange1_name = st.selectbox("1st Exchange", exchange_dict)
with row[1]:
    exchange2_name = st.selectbox("2nd Exchange", {k: v for k, v in exchange_dict.items() if k != exchange1_name})

# Find common symbols
exchange1 = exchange_dict[exchange1_name]
exchange2 = exchange_dict[exchange2_name]


def find_common_symbols(ex1: BaseExchange, ex2: BaseExchange):
    return [s for s in ex1.get_symbols() & ex2.get_symbols()]


def initialize_spread_dataframe(ex1: BaseExchange, ex2: BaseExchange) -> pd.DataFrame:
    common_symbols = find_common_symbols(exchange1, exchange2)
    st.info(f"🔄 공통 비교 가능 종목 수: {len(common_symbols)}")
    data_dict = defaultdict(list)
    ex1_tickers = ex1.get_tickers()
    if ex1_tickers:
        ex1_prices = {k: v for k, v in zip(ex1_tickers['symbol'], ex1_tickers['price'])}
        ex1_volumes = {k: v for k, v in zip(ex1_tickers['symbol'], ex1_tickers['volume'])}
        ex1_funding_rate = {k: v for k, v in zip(ex1_tickers['symbol'], ex1_tickers['funding_rate'])}
    else:
        ex1_prices = ex1.get_prices()
        ex1_volumes = ex1.get_24h_volume()
        ex1_funding_rate = ex1.get_funding_rates()
    ex2_tickers = ex2.get_tickers()
    if ex2_tickers:
        ex2_prices = {k: v for k, v in zip(ex2_tickers['symbol'], ex2_tickers['price'])}
        ex2_volumes = {k: v for k, v in zip(ex2_tickers['symbol'], ex2_tickers['volume'])}
        ex2_funding_rate = {k: v for k, v in zip(ex2_tickers['symbol'], ex2_tickers['fundingRate'])}
    else:
        ex2_prices = ex2.get_prices()
        ex2_volumes = ex2.get_24h_volume()
        ex2_funding_rate = ex2.get_funding_rates()

    for symbol in common_symbols:
        spread = ex1_prices[symbol] - ex2_prices[symbol]
        spread_pct = abs(spread / ex1_prices[symbol]) * 100 if ex1_prices[symbol] != 0 else 0

        data_dict["symbol"].append(symbol)
        data_dict["ex1_price"].append(ex1_prices[symbol])
        data_dict["ex2_price"].append(ex2_prices[symbol])
        data_dict["spread"].append(spread)
        data_dict["spread_pct"].append(spread_pct)
        data_dict["ex1_volume"].append(ex1_volumes[symbol])
        data_dict["ex2_volume"].append(ex2_volumes[symbol])
        data_dict["ex1_funding_rate"].append(ex1_funding_rate[symbol])
        data_dict["ex2_funding_rate"].append(ex2_funding_rate[symbol])
    df = pd.DataFrame(data_dict)  # , index=['symbol'])
    df.set_index("symbol", inplace=True)
    return df


df = initialize_spread_dataframe(exchange1, exchange2)
df.sort_values(by='spread_pct', ascending=False, inplace=True)
st.dataframe(df,
    column_config={
        "symbol": "Symbol",
        "ex1_price": NumberColumn(f"{exchange1.get_exchange_name()}가격", format="$%.4g"),
        "ex2_price": NumberColumn(f"{exchange2.get_exchange_name()}가격", format="$%.4g"),
        "spread": NumberColumn("차이", format="$%.5g"),
        "spread_pct": NumberColumn("차이율", format="%.2f%%"),
        "ex1_volume": NumberColumn(f"{exchange1.get_exchange_name()}거래량", format="%d"),
        "ex2_volume": NumberColumn(f"{exchange2.get_exchange_name()}거래량", format="%d"),
        "ex1_funding_rate": NumberColumn(f"{exchange1.get_exchange_name()}펀딩피(%)", format="%.4g%%"),
        "ex2_funding_rate": NumberColumn(f"{exchange2.get_exchange_name()}펀딩피(%)", format="%.4g%%"),
        "chart": LineChartColumn(
            "차트", width=100),
    })