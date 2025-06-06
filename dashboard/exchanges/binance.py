from datetime import datetime

import requests
import pandas as pd
import streamlit as st


@st.cache_data(ttl=30)  # 30초 동안 캐시 유효
def get_binance_funding_rates():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item["symbol"]: float(item["lastFundingRate"]) * 100 for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}


@st.cache_data(ttl=30)
def get_binance_24h_volume():
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item['symbol']: float(item['quoteVolume']) for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 거래량 정보를 불러올 수 없습니다: {e}")
        return {}


@st.cache_data(ttl=30)
def get_binance_futures_symbols():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return set(
            item['symbol']
            for item in data.get('symbols', [])
            if item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
        )
    except Exception as e:
        st.error(f"❌ Binance 심볼 정보를 불러올 수 없습니다: {e}")
        return set()


@st.cache_data(ttl=30)
def get_binance_prices():
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {item['symbol']: float(item['price']) for item in r.json()}
    except Exception as e:
        st.error(f"❌ Binance 가격 정보를 불러올 수 없습니다: {e}")
        return {}


@st.cache_data(ttl=300)
def get_binance_klines(symbol, minutes):
    try:
        end_time = int(datetime.utcnow().timestamp() * 1000)
        start_time = end_time - minutes * 60 * 1000
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&startTime={start_time}&endTime={end_time}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                         "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
                                         "taker_buy_quote_volume", "ignore"])
        df["binance_price"] = df["close"].astype(float)
        df["index"] = range(len(df))
        return df[["index", "binance_price"]]
    except Exception as e:
        st.error(f"❌ Binance 과거 데이터 오류: {e}")
        return pd.DataFrame()
