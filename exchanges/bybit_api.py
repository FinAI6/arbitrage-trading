from collections import defaultdict
from typing import Dict, Set, List, Tuple, Any
import requests
import pandas as pd
from .base_exchange import BaseExchange
from dashboard.constants import *


def fetch_bybit_data(endpoint: str, params: Dict[str, Any] = {}) -> List[Dict]:
    try:
        url = f"https://api.bybit.com/v5/market/{endpoint}"
        r = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json().get("result", {}).get("list", [])
    except Exception as e:
        print(f"❌ Bybit API 호출 실패 ({endpoint}): {e}")
        return []


def get_bybit_tickers() -> defaultdict[str, list]:
    data = fetch_bybit_data("tickers", {"category": "linear"})
    ret = defaultdict(list)

    for item in data:
        try:
            if float(item.get("lastPrice", 0)) == 0:
                continue
            ret["symbol"].append(item["symbol"])
            ret["price"].append(float(item["lastPrice"]))
            ret["volume"].append(item["volume24h"])
            ret["fundingRate"].append(item["fundingRate"])
        except KeyError:
            continue

    return ret


def get_bybit_prices() -> Tuple[Dict[str, float], Set[str]]:
    data = fetch_bybit_data("tickers", {"category": "linear"})
    prices = {}
    symbols = set()

    for item in data:
        try:
            symbol = item["symbol"]
            prices[symbol] = float(item["lastPrice"])
            symbols.add(symbol)
        except KeyError:
            continue

    return prices, symbols


def get_bybit_funding_rates() -> Dict[str, float]:
    data = fetch_bybit_data("tickers", {"category": "linear"})
    return {
        item["symbol"]: float(item["fundingRate"]) * 100
        for item in data
        if item.get("fundingRate") not in (None, "", "null")
    }


def get_bybit_klines(symbol: str, minutes: int) -> pd.DataFrame:
    data = fetch_bybit_data("kline", {
        "category": "linear",
        "symbol": symbol,
        "interval": "1",
        "limit": minutes
    })

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["bybit_price"] = df["close"].astype(float)
    df["index"] = range(len(df))
    return df[["index", "bybit_price"]]


class BybitExchange(BaseExchange):
    """Bybit exchange API implementation using cached functions"""

    def get_exchange_name(self) -> str:
        return "Bybit"

    def get_tickers(self) -> defaultdict[str, list]:
        return get_bybit_tickers()

    def get_funding_rates(self) -> Dict[str, float]:
        return get_bybit_funding_rates()

    def get_24h_volume(self) -> Dict[str, float]:
        prices, _ = get_bybit_prices()
        data = fetch_bybit_data("tickers", {"category": "linear"})
        return {
            item["symbol"]: float(item["volume24h"]) * prices.get(item["symbol"], 0)
            for item in data
            if item.get("volume24h") is not None
        }

    def get_symbols(self) -> Set[str]:
        _, symbols = get_bybit_prices()
        return symbols

    def get_prices(self) -> Dict[str, float]:
        prices, _ = get_bybit_prices()
        return prices

    def get_klines(self, symbol: str, minutes: int) -> pd.DataFrame:
        return get_bybit_klines(symbol, minutes)
