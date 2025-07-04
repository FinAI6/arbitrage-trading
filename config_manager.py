import configparser
import os
from typing import Any, Dict, Optional


class ConfigManager:
    """
    Singleton class for managing configuration settings.
    Reads from and writes to a config.ini file.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._config_file = 'config.ini'
        self._config = configparser.ConfigParser()
        
        # Create config file if it doesn't exist
        if not os.path.exists(self._config_file):
            self._create_default_config()
        else:
            self._config.read(self._config_file)
            
        self._initialized = True
    
    def _create_default_config(self):
        """Create a default configuration file if none exists."""
        # Add default sections and values
        self._config['DEFAULT'] = {
            'max_deque_length': '100',
            'display_interval': '5',
            'test_duration': '0'
        }
        
        self._config['SYMBOLS'] = {
            'enabled': 'false',
            'symbols': 'BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,MATICUSDT,DOTUSDT,LTCUSDT'
        }
        
        self._config['EXCHANGES'] = {
            'binance_enabled': 'true',
            'bybit_enabled': 'true'
        }
        
        # Write to file
        with open(self._config_file, 'w') as f:
            self._config.write(f)
    
    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            section: The section in the config file
            key: The key to retrieve
            fallback: Default value if key doesn't exist
            
        Returns:
            The configuration value
        """
        return self._config.get(section, key, fallback=fallback)
    
    def getint(self, section: str, key: str, fallback: Optional[int] = None) -> int:
        """Get a configuration value as an integer."""
        return self._config.getint(section, key, fallback=fallback)
    
    def getfloat(self, section: str, key: str, fallback: Optional[float] = None) -> float:
        """Get a configuration value as a float."""
        return self._config.getfloat(section, key, fallback=fallback)
    
    def getboolean(self, section: str, key: str, fallback: Optional[bool] = None) -> bool:
        """Get a configuration value as a boolean."""
        return self._config.getboolean(section, key, fallback=fallback)
    
    def set(self, section: str, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            section: The section in the config file
            key: The key to set
            value: The value to set
        """
        # Create section if it doesn't exist
        if not self._config.has_section(section) and section != 'DEFAULT':
            self._config.add_section(section)
            
        self._config.set(section, key, str(value))
    
    def save(self) -> None:
        """Save the current configuration to the config file."""
        with open(self._config_file, 'w') as f:
            self._config.write(f)
    
    def get_all(self) -> Dict[str, Dict[str, str]]:
        """
        Get all configuration values.
        
        Returns:
            A dictionary containing all configuration values
        """
        result = {}
        for section in self._config.sections():
            result[section] = dict(self._config[section])
        result['DEFAULT'] = dict(self._config['DEFAULT'])
        return result
    
    def get_symbols(self) -> list:
        """
        Get the list of symbols from the config.
        
        Returns:
            A list of symbol strings if enabled, otherwise an empty list
        """
        if self.getboolean('SYMBOLS', 'enabled', fallback=False):
            symbols_str = self.get('SYMBOLS', 'symbols', fallback='')
            return [s.strip() for s in symbols_str.split(',') if s.strip()]
        return []
