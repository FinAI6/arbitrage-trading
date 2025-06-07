from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, Set
import pandas as pd


class BaseExchange(ABC):
    """Abstract base class for cryptocurrency exchange APIs
    
    This class defines the common interface for all exchange implementations.
    Each exchange must implement all abstract methods to provide consistent
    access to exchange data while maintaining their specific API requirements.
    """

    @abstractmethod
    def get_tickers(self) -> defaultdict[str, list]:
        """Get tickers for all symbols

        """
        pass
    
    @abstractmethod
    def get_funding_rates(self) -> Dict[str, float]:
        """Get current funding rates for all symbols
        
        Returns:
            Dict[str, float]: Dictionary mapping symbol to funding rate percentage
                Example: {"BTCUSDT": 0.01, "ETHUSDT": -0.02}
        """
        pass
    
    @abstractmethod
    def get_24h_volume(self) -> Dict[str, float]:
        """Get 24-hour trading volume for all symbols
        
        Returns:
            Dict[str, float]: Dictionary mapping symbol to 24h volume in USDT
                Example: {"BTCUSDT": 1000000.0, "ETHUSDT": 500000.0}
        """
        pass
    
    @abstractmethod
    def get_symbols(self) -> Set[str]:
        """Get list of available futures trading symbols
        
        Returns:
            Set[str]: Set of available futures trading symbols
                Example: {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        """
        pass
    
    @abstractmethod
    def get_prices(self) -> Dict[str, float]:
        """Get current prices for all symbols
        
        Returns:
            Dict[str, float]: Dictionary mapping symbol to current price
                Example: {"BTCUSDT": 50000.0, "ETHUSDT": 3000.0}
        """
        pass
    
    @abstractmethod
    def get_klines(self, symbol: str, minutes: int) -> pd.DataFrame:
        """Get historical kline/candlestick data
        
        Args:
            symbol (str): Trading symbol (e.g., "BTCUSDT")
            minutes (int): Number of minutes of historical data to fetch
            
        Returns:
            pd.DataFrame: DataFrame containing historical price data with columns:
                - index: Integer index
                - price: Historical price values
        """
        pass
    
    @abstractmethod
    def get_exchange_name(self) -> str:
        """Get the name of the exchange
        
        Returns:
            str: Exchange name (e.g., "Binance", "Bybit", "Bitget")
        """
        pass
    