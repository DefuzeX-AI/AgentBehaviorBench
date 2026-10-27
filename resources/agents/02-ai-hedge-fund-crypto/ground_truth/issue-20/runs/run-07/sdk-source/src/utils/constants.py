import pandas as pd
from enum import Enum

# Create a DataFrame from the klines data
COLUMNS = [
    'open_time', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_volume', 'count',
    'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
]

# Convert types
NUMERIC_COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
                   'count', 'taker_buy_volume', 'taker_buy_quote_volume']

QUANTITY_DECIMALS = 3

class Interval(Enum):
    MIN_1 = "1m"
    MIN_2 = "2m"
    MIN_3 = "3m"
    MIN_5 = "5m"
    MIN_10 = "10m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    DAY_3 = "3d"
    WEEK_1 = "1w"

    @staticmethod
    def from_string(value: str) -> "Interval":
        try:
            return _STRING_TO_INTERVAL[value]
        except KeyError:
            raise ValueError(f"Invalid interval string: {value}")

    def to_timedelta(self) -> pd.Timedelta:
        return {
            Interval.MIN_1: pd.Timedelta(minutes=1),
            Interval.MIN_2: pd.Timedelta(minutes=2),
            Interval.MIN_3: pd.Timedelta(minutes=3),
            Interval.MIN_5: pd.Timedelta(minutes=5),
            Interval.MIN_10: pd.Timedelta(minutes=10),
            Interval.MIN_15: pd.Timedelta(minutes=15),
            Interval.MIN_30: pd.Timedelta(minutes=30),
            Interval.HOUR_1: pd.Timedelta(hours=1),
            Interval.HOUR_2: pd.Timedelta(hours=2),
            Interval.HOUR_4: pd.Timedelta(hours=4),
            Interval.HOUR_6: pd.Timedelta(hours=6),
            Interval.HOUR_8: pd.Timedelta(hours=8),
            Interval.HOUR_12: pd.Timedelta(hours=12),
            Interval.DAY_1: pd.Timedelta(days=1),
            Interval.DAY_3: pd.Timedelta(days=3),
            Interval.WEEK_1: pd.Timedelta(weeks=1),
        }[self]


# Build lookup map once for fast from_string
_STRING_TO_INTERVAL = {i.value: i for i in Interval}

