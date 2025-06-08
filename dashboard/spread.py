from collections import defaultdict
from dataclasses import dataclass
from typing import Dict

import pandas as pd
from exchanges import BaseExchange
from exchanges.base_exchange import Ticker


# def get_tickers(exchange: BaseExchange) -> Dict[str, Ticker]:
#     tickers = exchange.get_tickers()
#     ret_dict = {}
#     for i, symbol in enumerate(tickers['symbol']):
#         ret_dict[symbol] = Ticker(symbol, tickers['price'][i],
#                                   tickers['volume'][i], tickers['fundingRate'][i])
#     return ret_dict


def create_spread_dataframe(ex1: BaseExchange, ex2: BaseExchange) -> pd.DataFrame:
    data_dict = defaultdict(list)
    ex1_tickers = ex1.get_tickers()
    ex2_tickers = ex2.get_tickers()
    common_symbols = [s for s in set(ex1_tickers.keys()) & set(ex2_tickers.keys())]
    for symbol in common_symbols:
        ticker1: Ticker = ex1_tickers[symbol]
        ticker2: Ticker = ex2_tickers[symbol]
        if ticker1.price == 0 or ticker2.price == 0:
            continue
        spread = ticker1.price - ticker2.price
        spread_pct = abs(spread / ticker1.price) * 100

        data_dict["symbol"].append(symbol)
        data_dict["ex1_price"].append(ticker1.price)
        data_dict["ex2_price"].append(ticker2.price)
        data_dict["spread"].append(spread)
        data_dict["spread_pct"].append(spread_pct)
        data_dict["chart"].append([])
        data_dict["ex1_volume"].append(ticker1.volume)
        data_dict["ex2_volume"].append(ticker2.volume)
        data_dict["ex1_funding_rate"].append(ticker1.funding_rate)
        data_dict["ex2_funding_rate"].append(ticker2.funding_rate)
    df = pd.DataFrame(data_dict)  # , index=['symbol'])
    df.set_index("symbol", inplace=True)
    return df
