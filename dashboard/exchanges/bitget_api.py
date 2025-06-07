from collections import defaultdict
from typing import Dict, Set, List, Tuple, Any
import requests
import pandas as pd
import streamlit as st
from .base_exchange import BaseExchange
from dashboard.constants import *

PRODUCT_TYPE = "USDT-FUTURES"


def fetch_bitget_data(endpoint: str, params: Dict[str, Any] = {}) -> List[Dict]:
    try:
        url = f"https://api.bitget.com/api/v2/mix/market/{endpoint}"
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        st.error(f"❌ Bitget API 호출 실패 ({endpoint}): {e}")
        return []


@st.cache_data(ttl=ST_CACHE_TTL)
def get_bitget_tickers() -> defaultdict[str, list]:
    data = fetch_bitget_data("tickers", {"productType": PRODUCT_TYPE})
    ret = defaultdict(list)

    for item in data:
        if float(item.get("lastPr", 0)) == 0:
            continue
        try:
            ret["symbol"].append(item["symbol"])
            ret["price"].append(float(item["lastPr"]))
            ret["volume"].append(item["baseVolume"])
            ret["fundingRate"].append(item["fundingRate"])
        except KeyError:
            continue
    return ret


@st.cache_data(ttl=ST_CACHE_TTL)
def get_bitget_prices() -> Tuple[Dict[str, float], Set[str]]:
    data = fetch_bitget_data("tickers", {"productType": PRODUCT_TYPE})
    prices, original_symbols = {}, {}

    for item in data:
        symbol = item.get("symbol")
        price = item.get("lastPr")
        if not symbol or price is None:
            continue

        normalized = symbol.replace("-", "").split("_")[0]
        prices[normalized] = float(price)
        original_symbols[normalized] = symbol

    return prices, set(prices.keys())


@st.cache_data(ttl=ST_CACHE_TTL)
def get_bitget_funding_rates() -> Dict[str, float]:
    data = fetch_bitget_data("tickers", {"productType": PRODUCT_TYPE})
    return {
        item["symbol"]: float(item["fundingRate"]) * 100
        for item in data
        if item.get("fundingRate") not in (None, "", "null")
    }


@st.cache_data(ttl=ST_CACHE_TTL_KLINES)
def get_bitget_klines(symbol: str, minutes: int) -> pd.DataFrame:
    data = fetch_bitget_data("candles", {
        "symbol": symbol,
        "granularity": "1m",
        "limit": minutes
    })

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["bitget_price"] = df["close"].astype(float)
    df["index"] = range(len(df))
    return df[["index", "bitget_price"]]


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
        data = fetch_bitget_data("tickers", {"productType": PRODUCT_TYPE})
        return {
            item["symbol"]: float(item["usdtVolume"]) * prices.get(item["symbol"], 0)
            for item in data
            if item.get("usdtVolume") is not None
        }

    def get_symbols(self) -> Set[str]:
        tickers = get_bitget_tickers()
        return set(tickers['symbol'])

    def get_prices(self) -> Dict[str, float]:
        prices, _ = get_bitget_prices()
        return prices

    def get_klines(self, symbol: str, minutes: int) -> pd.DataFrame:
        return get_bitget_klines(symbol, minutes)
