import requests
import pandas as pd
import streamlit as st


@st.cache_data(ttl=30)
def get_bybit_prices():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get('result', {}).get('list', [])
        return {item['symbol']: float(item['lastPrice']) for item in data}, set(item['symbol'] for item in data)
    except Exception as e:
        st.error(f"❌ Bybit 가격 정보를 불러올 수 없습니다: {e}")
        return {}, set()


@st.cache_data(ttl=30)
def get_bybit_funding_rates():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("result", {}).get("list", [])
        return {
            item["symbol"]: float(item["fundingRate"]) * 100
            for item in data if item.get("fundingRate") not in (None, '', 'null')
        }
    except Exception as e:
        st.error(f"❌ Bybit 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}


@st.cache_data(ttl=300)
def get_bybit_klines(symbol, minutes):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit={minutes}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json().get("result", {}).get("list", [])
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["bybit_price"] = df["close"].astype(float)
        df["index"] = range(len(df))
        return df[["index", "bybit_price"]]
    except Exception as e:
        st.error(f"❌ Bybit 과거 데이터 오류: {e}")
        return pd.DataFrame()
