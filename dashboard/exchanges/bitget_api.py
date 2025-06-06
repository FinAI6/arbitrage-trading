from collections import defaultdict
from typing import Dict, Set
import requests
import pandas as pd
import streamlit as st
from .base_exchange import BaseExchange


@st.cache_data(ttl=30)
def get_bitget_tickers():
    try:
        url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get('data', [])
        ret_dict = defaultdict(list)
        for item in data:
            if 'fundingRate' not in item or 'baseVolume' not in item or 'lastPr' not in item:
                continue
            ret_dict['symbol'].append(item['symbol'])
            ret_dict['price'].append(float(item['lastPr']))
            ret_dict['volume'].append(item['baseVolume'])
            ret_dict['fundingRate'].append(item['fundingRate'])
        return ret_dict
    except Exception as e:
        st.error(f"❌ Bitget 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}


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

        return prices, set(prices.keys())

    except Exception as e:
        st.error(f"❌ Bitget 가격 정보를 불러올 수 없습니다: {e}")
        return {}, set(), {}


@st.cache_data(ttl=30)
def get_bitget_funding_rates():
    try:
        url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get('data', [])
        return {
            item['symbol']: float(item['fundingRate']) * 100
            for item in data if item.get('fundingRate') not in (None, '', 'null')
        }
    except Exception as e:
        st.error(f"❌ Bitget 펀딩피 정보를 불러올 수 없습니다: {e}")
        return {}


@st.cache_data(ttl=300)
def get_bitget_klines(symbol, minutes):
    try:
        url = f"https://api.bitget.com/api/v2/mix/market/candles?symbol={symbol}&granularity=1m&limit={minutes}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json().get('data', [])
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["bitget_price"] = df["close"].astype(float)
        df["index"] = range(len(df))
        return df[["index", "bitget_price"]]
    except Exception as e:
        st.error(f"❌ Bitget 과거 데이터 오류: {e}")
        return pd.DataFrame()


class BitgetExchange(BaseExchange):
    """Bitget exchange API implementation using cached functions"""

    def get_exchange_name(self) -> str:
        return "Bitget"

    def get_tickers(self) -> defaultdict[str, list]:
        return get_bitget_tickers()

    def get_funding_rates(self) -> Dict[str, float]:
        return get_bitget_funding_rates()

    def get_24h_volume(self) -> Dict[str, float]:
        prices, _ = get_bitget_prices()
        try:
            url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json().get('data', [])
            return {item['symbol']: float(item['usdtVolume']) * prices.get(item['symbol'], 0) for item in data}
        except Exception as e:
            st.error(f"❌ Bitget 거래량 정보를 불러올 수 없습니다: {e}")
            return {}

    def get_symbols(self) -> Set[str]:
        tickers = get_bitget_tickers()
        return set(tickers['symbol'])

    def get_prices(self) -> Dict[str, float]:
        prices, _ = get_bitget_prices()
        return prices

    def get_klines(self, symbol: str, minutes: int) -> pd.DataFrame:
        return get_bitget_klines(symbol, minutes)
