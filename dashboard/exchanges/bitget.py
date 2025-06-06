import requests
import streamlit as st


@st.cache_data(ttl=30)
def get_bitget_prices():
    try:
        url = "https://api.bitget.com/api/mix/v1/market/tickers?productType=umcbl"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])

        prices = {}
        original_symbols = {}

        for item in data:
            raw_symbol = item.get("symbol", "")  # 예: BTCUSDT_UMCBL, ETHUSDT
            if not raw_symbol or "last" not in item:
                continue

            # 정규화: BTC-USDT → BTCUSDT, BTCUSDT_UMCBL → BTCUSDT
            normalized = raw_symbol.replace("-", "").split("_")[0]

            prices[normalized] = float(item["last"])
            original_symbols[normalized] = raw_symbol

        return prices, set(prices.keys()), original_symbols

    except Exception as e:
        st.error(f"❌ Bitget 가격 정보를 불러올 수 없습니다: {e}")
        return {}, set(), {}


@st.cache_data(ttl=30)
def get_bitget_funding_rates():
    try:
        url = "https://api.bitget.com/api/v2/mix/market/funding-rate?productType=umcbl"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        return {
            item["symbol"]: float(item["fundingRate"]) * 100
            for item in data if item.get("fundingRate")
        }
    except Exception as e:
        st.error(f"❌ Bitget 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}
