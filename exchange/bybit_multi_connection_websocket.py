import asyncio
import math
from typing import List, Dict, Any
from .bybit_orderbook_websocket import BybitOrderbookWebsocket


class BybitMultiConnectionWebsocket:
    """
    Wrapper class that manages multiple BybitOrderbookWebsocket connections
    to distribute symbols across multiple connections for better stability.
    """
    
    def __init__(self, symbols=None, test_duration=None, max_symbols_per_connection=50):
        """
        Initialize multiple Bybit WebSocket connections
        
        Args:
            symbols (list): List of symbols to subscribe to
            test_duration (int): Test duration in seconds
            max_symbols_per_connection (int): Maximum symbols per connection (default: 50)
        """
        self.symbols = symbols or []
        self.test_duration = test_duration
        self.max_symbols_per_connection = max_symbols_per_connection
        self.connections: List[BybitOrderbookWebsocket] = []
        self.running = False
        
    async def fetch_all_symbols(self):
        """
        Fetch all available symbols using a single connection
        """
        # Create a temporary connection to fetch symbols
        temp_client = BybitOrderbookWebsocket()
        symbols = await temp_client.fetch_all_symbols()
        return symbols
        
    def set_symbols(self, symbols):
        """
        Set symbols and create multiple connections to distribute them
        """
        self.symbols = symbols
        
    def _create_connections(self):
        """
        Create multiple connections and distribute symbols among them
        """
        if not self.symbols:
            return
            
        # Calculate number of connections needed
        num_connections = math.ceil(len(self.symbols) / self.max_symbols_per_connection)
        
        # Ensure we have at least 7 connections as requested
        num_connections = max(num_connections, 7)
        
        # Distribute symbols across connections
        symbols_per_connection = math.ceil(len(self.symbols) / num_connections)
        
        self.connections = []
        for i in range(num_connections):
            start_idx = i * symbols_per_connection
            end_idx = min(start_idx + symbols_per_connection, len(self.symbols))
            
            if start_idx < len(self.symbols):
                connection_symbols = self.symbols[start_idx:end_idx]
                connection = BybitOrderbookWebsocket(
                    symbols=connection_symbols,
                    test_duration=self.test_duration
                )
                self.connections.append(connection)
                
        print(f"Created {len(self.connections)} Bybit WebSocket connections")
        for i, conn in enumerate(self.connections):
            print(f"  Connection {i+1}: {len(conn.symbols)} symbols")
            
    async def connect(self):
        """
        Connect all WebSocket connections
        """

        if not self.symbols:
            self.symbols = await self.fetch_all_symbols()

        self._create_connections()

        if not self.connections:
            print("No connections to start. Make sure to call set_symbols() first.")
            return
            
        self.running = True
        
        # Start all connections concurrently
        connection_tasks = []
        for i, connection in enumerate(self.connections):
            task = asyncio.create_task(connection.connect())
            connection_tasks.append(task)
            
        print(f"Starting {len(connection_tasks)} Bybit WebSocket connections...")
        
        try:
            await asyncio.gather(*connection_tasks, return_exceptions=True)
        except Exception as e:
            print(f"Error in Bybit multi-connection WebSocket: {e}")
        finally:
            self.running = False
            
    def get_data(self) -> Dict[str, Any]:
        """
        Aggregate data from all connections
        
        Returns:
            dict: Combined data from all connections
        """
        combined_data = {}
        
        for connection in self.connections:
            connection_data = connection.get_data()
            combined_data.update(connection_data)
            
        return combined_data
        
    async def stop(self):
        """
        Stop all WebSocket connections
        """
        self.running = False
        
        if self.connections:
            stop_tasks = []
            for connection in self.connections:
                task = asyncio.create_task(connection.stop())
                stop_tasks.append(task)
                
            await asyncio.gather(*stop_tasks, return_exceptions=True)
            print("All Bybit WebSocket connections stopped")