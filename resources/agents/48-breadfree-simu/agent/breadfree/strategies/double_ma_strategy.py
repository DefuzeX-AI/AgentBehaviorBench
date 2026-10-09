import pandas as pd
from .base_strategy import BreadFreeStrategy
from ..utils.logger import get_logger

logger = get_logger(__name__)

class DoubleMAStrategy(BreadFreeStrategy):
    def __init__(self, broker, lot_size=100, short_window=5, long_window=20):
        super().__init__(broker, lot_size)
        self.short_window = short_window
        self.long_window = long_window
        self.history = []
        self.symbol = None

    def set_symbol(self, symbol):
        self.symbol = symbol

    def on_bar(self, date, bar_data):
        self.history.append(bar_data['close'])
        
        if len(self.history) < self.long_window:
            return

        # Calculate MAs
        prices = pd.Series(self.history)
        short_ma = prices.rolling(window=self.short_window).mean().iloc[-1]
        long_ma = prices.rolling(window=self.long_window).mean().iloc[-1]
        
        # Previous MAs for crossover check
        prev_short_ma = prices.rolling(window=self.short_window).mean().iloc[-2]
        prev_long_ma = prices.rolling(window=self.long_window).mean().iloc[-2]

        close_price = bar_data['close']

        # Golden Cross (Short crosses above Long)
        if prev_short_ma <= prev_long_ma and short_ma > long_ma:
            logger.info(f"[{date}] Golden Cross: Buying")
            self.buy(date, close_price)

        # Death Cross (Short crosses below Long)
        elif prev_short_ma >= prev_long_ma and short_ma < long_ma:
            logger.info(f"[{date}] Death Cross: Selling")
            self.sell(date, close_price)

    def buy(self, date, price):
        # Buy using 90% of available cash to avoid margin issues
        available_cash = self.broker.cash
        target_cash = available_cash * 0.9
        
        if target_cash > 0:
            max_shares = int(target_cash / (price * (1 + self.broker.commission_rate)))
            quantity = (max_shares // self.lot_size) * self.lot_size
            
            if quantity > 0:
                self.broker.buy(date, self.symbol, price, quantity)

    def sell(self, date, price):
        if self.symbol in self.broker.positions:
            pos = self.broker.positions[self.symbol]
            if pos.quantity > 0:
                self.broker.sell(date, self.symbol, price, pos.quantity)
