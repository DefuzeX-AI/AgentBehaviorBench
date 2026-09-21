"""
Binance Data Provider Module

This module handles retrieving data from Binance and preparing it for the trading system.
"""

from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from src.gateway.binance.client import Client
from src.utils.constants import COLUMNS, NUMERIC_COLUMNS


class BinanceDataProvider:
    """
    Class to handle data retrieval from Binance and prepare it for the trading system.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize the BinanceDataProvider with API credentials.

        Args:
            api_key: Binance API key (optional for public data)
            api_secret: Binance API secret (optional for public data)
        """
        self.client = Client(api_key=api_key, api_secret=api_secret)

        # Create cache directory if it doesn't exist
        self.cache_dir = Path("./cache")
        self.cache_dir.mkdir(exist_ok=True)

    def _format_timeframe(self, timeframe: str) -> str:
        """
        Convert our timeframe format to Binance's format.

        Args:
            timeframe: Timeframe in format like '1h', '5m', '1d'

        Returns:
            Binance format of the timeframe
        """
        # Binance uses the same format as our system
        return timeframe

    def get_historical_klines(
            self,
            symbol: str,
            timeframe: str,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get historical klines (candlestick data) for a symbol and timeframe.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframe: Time interval (e.g., '1h', '5m', '1d')
            start_date: Start date for historical data
            end_date: End date for historical data
            use_cache: Whether to use cached data if available

        Returns:
            DataFrame with historical price data
        """
        # Format the symbol if needed (remove / if present)
        formatted_symbol = symbol.replace("/", "")

        # Default to 30 days of data if no start date is provided
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)

        if end_date is None:
            end_date = datetime.now()

        # Create cache file path
        cache_file = self.cache_dir / f"{formatted_symbol}_{timeframe}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"

        # Check if cache file exists and is fresh
        if use_cache and cache_file.exists():
            print(f"Loading cached data for {formatted_symbol} {timeframe}")
            return pd.read_csv(cache_file, parse_dates=['open_time', 'close_time'])

        print(f"Fetching historical data for {formatted_symbol} {timeframe}")

        # Convert datetime to milliseconds timestamp
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        try:
            # Use the client to get historical klines
            klines = self.client.get_historical_klines(
                symbol=formatted_symbol,
                interval=self._format_timeframe(timeframe),
                start_str=start_ts,
                end_str=end_ts
            )

            df = pd.DataFrame(klines, columns=COLUMNS)
            # Convert types
            for col in NUMERIC_COLUMNS:
                df[col] = pd.to_numeric(df[col])

            # Convert timestamps to datetime
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

            # Cache the data
            if use_cache:
                df.to_csv(cache_file, index=False)

            return df

        except Exception as e:
            print(f"Error fetching historical data for {formatted_symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def get_multiple_timeframes_with_end_time(
            self,
            symbol: str,
            timeframes: List[str],
            end_time: str,
            limit: int = 500,
    ) -> Dict[str, pd.DataFrame]:
        """
        Get data for multiple timeframes for a single symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframes: List of timeframes (e.g., ['5m', '15m', '1h'])
            end_time: end time for multiple timeframes
            limit: Maximum number of timeframes to fetch
        Returns:
            Dictionary of DataFrames for each timeframe
        """
        result = {}
        for timeframe in timeframes:
            df = self.get_history_klines_with_end_time(symbol=symbol, timeframe=timeframe, end_time=end_time,
                                                       limit=limit)
            result[timeframe] = df
            # formatted_symbol = symbol.replace("/", "")
            # try:
            #     # Use the client to get klines
            #     klines = self.client.futures_historical_klines_with_end_time(
            #         symbol=formatted_symbol,
            #         interval=self._format_timeframe(timeframe),
            #         end_str=end_time,
            #         limit=limit
            #     )
            #
            #     # Create a DataFrame from the klines data
            #     columns = [
            #         'open_time', 'open', 'high', 'low', 'close', 'volume',
            #         'close_time', 'quote_volume', 'count',
            #         'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
            #     ]
            #
            #     df = pd.DataFrame(klines, columns=columns)
            #
            #     # Convert types
            #     numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
            #                     'count', 'taker_buy_volume', 'taker_buy_quote_volume']
            #
            #     for col in numeric_cols:
            #         df[col] = pd.to_numeric(df[col])
            #
            #     # Convert timestamps to datetime
            #     df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            #     df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            #
            #     result[timeframe] = df
            #
            # except Exception as e:
            #     print(f"Error fetching latest data for {formatted_symbol} {timeframe}: {e}")
            #     result[timeframe] = pd.DataFrame()

        return result

    def get_history_klines_with_end_time(
            self,
            symbol: str,
            timeframe: str,
            end_time: datetime,
            limit: int = 500,
    ) -> pd.DataFrame:
        """
        Get data for multiple timeframes for a single symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframe: time interval (e.g., '1h', '5m', '1d')
            end_time: end time for timeframes data
            limit: Maximum number of timeframes to fetch
        Returns:
            Dictionary of DataFrames for each timeframe
        """
        formatted_symbol = symbol.replace("/", "")
        try:
            # Use the client to get klines
            klines = self.client.futures_historical_klines_with_end_time(
                symbol=formatted_symbol,
                interval=self._format_timeframe(timeframe),
                end_str=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                limit=limit
            )

            df = pd.DataFrame(klines, columns=COLUMNS)

            for col in NUMERIC_COLUMNS:
                df[col] = pd.to_numeric(df[col])

            # Convert timestamps to datetime
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

            return df

        except Exception as e:
            print(f"Error fetching latest data for {formatted_symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def get_latest_multi_timeframe_data(
            self,
            symbol: str,
            timeframes: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """
        Get data for multiple timeframes for a single symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframes: List of timeframes (e.g., ['5m', '15m', '1h'])
        Returns:
            Dictionary of DataFrames for each timeframe
        """
        result = {}

        for timeframe in timeframes:
            df = self.get_latest_data(
                symbol=symbol,
                timeframe=timeframe,
            )

            if not df.empty:
                result[timeframe] = df
            else:
                print(f"Warning: No data retrieved for {symbol} {timeframe}")
        return result

    def get_multi_timeframe_data(
            self,
            symbol: str,
            timeframes: List[str],
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Get data for multiple timeframes for a single symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframes: List of timeframes (e.g., ['5m', '15m', '1h'])
            start_date: Start date for historical data
            end_date: End date for historical data

        Returns:
            Dictionary of DataFrames for each timeframe
        """
        result = {}

        for timeframe in timeframes:
            df = self.get_historical_klines(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )

            if not df.empty:
                result[timeframe] = df
            else:
                print(f"Warning: No data retrieved for {symbol} {timeframe}")

        return result

    def get_latest_data(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        """
        Get the latest candlestick data for a symbol and timeframe.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            timeframe: Time interval (e.g., '1h', '5m', '1d')
            limit: Number of candles to retrieve

        Returns:
            DataFrame with the latest price data
        """
        # Format the symbol if needed
        formatted_symbol = symbol.replace("/", "")

        try:
            # Use the client to get klines
            klines = self.client.get_klines(
                symbol=formatted_symbol,
                interval=self._format_timeframe(timeframe),
                limit=limit
            )

            # Create a DataFrame from the klines data
            df = pd.DataFrame(klines, columns=COLUMNS)

            # Convert types
            for col in NUMERIC_COLUMNS:
                df[col] = pd.to_numeric(df[col])

            # Convert timestamps to datetime
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

            return df

        except Exception as e:
            print(f"Error fetching latest data for {formatted_symbol} {timeframe}: {e}")
            return pd.DataFrame()


# Simple test function
def test_data_provider():
    provider = BinanceDataProvider()
    symbol = "BTCUSDT"
    timeframe = "1h"

    # Get latest data
    df = provider.get_latest_data(symbol, timeframe, limit=10)
    print(f"Latest data for {symbol} {timeframe}:")
    print(df.head())

    # Get historical data
    start_date = datetime.now() - timedelta(days=7)
    df_hist = provider.get_historical_klines(symbol, timeframe, start_date)
    print(f"\nHistorical data for {symbol} {timeframe}:")
    print(f"Retrieved {len(df_hist)} records")
    print(df_hist.head())

    # Get multiple timeframes
    timeframes = ["5m", "15m", "1h"]
    multi_tf_data = provider.get_multi_timeframe_data(symbol, timeframes, start_date)
    for tf, tf_df in multi_tf_data.items():
        print(f"\nData for {symbol} {tf}:")
        print(f"Retrieved {len(tf_df)} records")
        print(tf_df.head())


if __name__ == "__main__":
    test_data_provider()
