from collections import defaultdict
from typing import Dict, Set, Any
from datetime import datetime
import requests
import pandas as pd
from .base_exchange import BaseExchange, Ticker
# from dashboard.constants import *

DEFAULT_TIMEOUT = 300

def fetch_binance_data(endpoint: str, params: Dict[str, Any] = {}) -> Any:
    try:
        url = f"https://fapi.binance.com/fapi/v1/{endpoint}"
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Binance API 호출 실패 ({endpoint}): {e}")
        return None


def get_binance_funding_rates() -> Dict[str, float]:
    data = fetch_binance_data("premiumIndex")
    if not data:
        return {}

    return {
        item["symbol"]: float(item["lastFundingRate"]) * 100
        for item in data
        if item.get("lastFundingRate") is not None
    }


def get_binance_24h_volume() -> Dict[str, float]:
    data = fetch_binance_data("ticker/24hr")
    if not data:
        return {}

    return {
        item["symbol"]: float(item["quoteVolume"])
        for item in data
        if item.get("quoteVolume") is not None
    }


def get_binance_symbols() -> Set[str]:
    data = fetch_binance_data("exchangeInfo")
    if not data:
        return set()

    return {
        item["symbol"]
        for item in data.get("symbols", [])
        if item.get("contractType") == "PERPETUAL"
           and item.get("quoteAsset") == "USDT"
           and item.get("status") == "TRADING"
    }


def get_binance_prices() -> Dict[str, float]:
    data = fetch_binance_data("ticker/price")
    if not data:
        return {}

    return {
        item["symbol"]: float(item["price"])
        for item in data
        if item.get("price") is not None
    }


def get_binance_klines(symbol: str, minutes: int) -> pd.DataFrame:
    end_time = int(datetime.utcnow().timestamp() * 1000)
    start_time = end_time - minutes * 60 * 1000

    data = fetch_binance_data("klines", {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_time,
        "endTime": end_time
    })

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
    ])

    df["binance_price"] = df["close"].astype(float)
    df["index"] = range(len(df))
    return df[["index", "binance_price"]]


class BinanceExchange(BaseExchange):
    """Binance exchange API implementation using cached functions"""

    def get_exchange_name(self) -> str:
        return "Binance"

    def get_tickers(self) -> Dict[str, Ticker]:
        prices = get_binance_prices()
        volumes = get_binance_24h_volume()
        funding_rates = get_binance_funding_rates()
        symbols = get_binance_symbols()

        ret = {}
        for symbol in symbols:
            if symbol in prices and symbol in volumes and symbol in funding_rates:
                ret[symbol] = Ticker(symbol, prices[symbol], volumes[symbol], funding_rates[symbol])
        return ret

    def get_funding_rates(self) -> Dict[str, float]:
        return get_binance_funding_rates()

    def get_24h_volume(self) -> Dict[str, float]:
        return get_binance_24h_volume()

    def get_symbols(self) -> Set[str]:
        return get_binance_symbols()

    def get_prices(self) -> Dict[str, float]:
        return get_binance_prices()

    def get_klines(self, symbol: str, minutes: int) -> pd.DataFrame:
        return get_binance_klines(symbol, minutes)
