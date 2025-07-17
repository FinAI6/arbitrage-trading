import logging
import sys
from datetime import datetime
from config_manager import ConfigManager

class LoggingManager:
    """Centralized logging configuration for the arbitrage trading system"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggingManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.config_manager = ConfigManager()
            self.setup_logging()
            LoggingManager._initialized = True
    
    def setup_logging(self):
        """Setup logging configuration with different levels and handlers"""
        
        # Get logging configuration from config file or use defaults
        try:
            log_level = self.config_manager.get('LOGGING', 'level', fallback='INFO').upper()
            log_to_file = self.config_manager.getboolean('LOGGING', 'log_to_file', fallback=True)
            log_file_path = self.config_manager.get('LOGGING', 'log_file_path', fallback='arbitrage_trading.log')
            console_log_level = self.config_manager.get('LOGGING', 'console_level', fallback='INFO').upper()
        except:
            # Fallback values if config is not available
            log_level = 'INFO'
            log_to_file = True
            log_file_path = 'arbitrage_trading.log'
            console_log_level = 'INFO'
        
        # Convert string levels to logging constants
        level_mapping = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        file_level = level_mapping.get(log_level, logging.INFO)
        console_level = level_mapping.get(console_log_level, logging.INFO)
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # Set to lowest level, handlers will filter
        
        # Clear any existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)
        
        # File handler (if enabled)
        if log_to_file:
            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setLevel(file_level)
            file_handler.setFormatter(detailed_formatter)
            root_logger.addHandler(file_handler)
    
    def get_logger(self, name):
        """Get a logger instance for a specific module"""
        return logging.getLogger(name)

# Convenience function to get logger
def get_logger(name=None):
    """Get a logger instance. If name is None, uses the calling module's name."""
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    # Initialize logging manager (singleton)
    LoggingManager()
    return logging.getLogger(name)

# Pre-configured loggers for common use cases
def get_trader_logger(symbol):
    """Get a logger specifically for trader modules"""
    return get_logger(f'trader.{symbol}')

def get_exchange_logger(exchange_name):
    """Get a logger specifically for exchange modules"""
    return get_logger(f'exchange.{exchange_name}')

def get_main_logger():
    """Get a logger for main application"""
    return get_logger('main')

def get_monitoring_logger():
    """Get a logger for monitoring"""
    return get_logger('monitoring')