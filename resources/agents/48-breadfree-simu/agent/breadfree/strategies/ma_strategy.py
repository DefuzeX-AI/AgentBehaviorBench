from .base_strategy import BreadFreeStrategy
import pandas as pd
import sys
import os
# Add the project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breadfree.utils.logger import get_logger

logger = get_logger(__name__)

class DoubleMAStrategy(BreadFreeStrategy):
    def __init__(self, broker, short_window=5, long_window=20, lot_size=100, max_position_pct: float = 1.0, **kwargs):
        """Double moving average strategy.

        Args:
            broker: Broker instance
            short_window: short MA window
            long_window: long MA window
            lot_size: minimal tradeable lot size
            max_position_pct: fraction of available cash to use when opening a position (0.0-1.0)
        """
        super().__init__(broker, lot_size=lot_size)
        self.params = kwargs
        self.short_window = short_window
        self.long_window = long_window
        self.max_position_pct = float(max_position_pct)

    def on_bar(self, date, bars):
        """
        :param date: datetime
        :param bars: {symbol: Series/dict}
        """
        # Iterate over all available symbols for this date
        for symbol, bar_data in bars.items():
            close_price = bar_data['close']

            # Validate price
            if pd.isna(close_price) or close_price <= 0:
                logger.warning(f"[{date}] Invalid close price for {symbol}: {close_price}. Skipping.")
                continue

            # Ensure history list exists
            if symbol not in self.history:
                self.history[symbol] = []
            elif not isinstance(self.history[symbol], list):
                hist = self.history[symbol]
                if isinstance(hist, pd.DataFrame):
                    if 'close' in hist.columns:
                        self.history[symbol] = hist['close'].tolist()
                    else:
                        self.history[symbol] = hist.iloc[:, -1].tolist()
                elif isinstance(hist, pd.Series):
                    self.history[symbol] = hist.tolist()
                else:
                    self.history[symbol] = list(hist)

            self.history[symbol].append(close_price)

            if len(self.history[symbol]) < self.long_window:
                continue

            # Calculate MAs
            hist_series = pd.Series(self.history[symbol])
            short_ma = hist_series.rolling(window=self.short_window).mean().iloc[-1]
            long_ma = hist_series.rolling(window=self.long_window).mean().iloc[-1]
            
            prev_short_ma = hist_series.rolling(window=self.short_window).mean().iloc[-2]
            prev_long_ma = hist_series.rolling(window=self.long_window).mean().iloc[-2]

            # Check for crossover
            # Golden Cross (Short crosses above Long) -> Buy
            if prev_short_ma <= prev_long_ma and short_ma > long_ma:
                # Buy signal
                if symbol not in self.broker.positions:
                    logger.info(f"[{date}] Golden Cross detected for {symbol}. Preparing to buy.")

                    available_cash = self.broker.cash
                    # 如果多只股票，这里的资金分配逻辑可能需要调整。
                    # 简单起见，我们假设每只股票最多使用当前可用资金的 max_position_pct / n (如果 n 已知)
                    # 或者，保持原逻辑：每只股票尝试使用 max_position_pct 的可用资金。
                    # 这意味着如果很多股票同时出信号，后面的可能买不到。
                    
                    target_cash = available_cash * max(0.0, min(1.0, self.max_position_pct))

                    # Estimate cost including commission
                    est_share_cost = close_price * (1 + self.broker.commission_rate)
                    if est_share_cost <= 0:
                        continue
                        
                    max_shares = int(target_cash / est_share_cost)
                    quantity = (max_shares // self.lot_size) * self.lot_size

                    if quantity == 0 and available_cash >= est_share_cost * self.lot_size and self.max_position_pct > 0:
                         quantity = self.lot_size

                    if quantity > 0:
                        logger.info(f"[{date}] Executing buy: symbol={symbol}, quantity={quantity}, price={close_price:.2f}")
                        self.broker.buy(date, symbol, close_price, quantity)

            # Death Cross (Short crosses below Long) -> Sell
            elif prev_short_ma >= prev_long_ma and short_ma < long_ma:
                # Sell signal
                sell_qty = None
                pos = None
                if symbol in self.broker.positions:
                    logger.info(f"[{date}] Death Cross detected for {symbol}. Preparing to sell.")
                    pos = self.broker.positions[symbol]
                    sell_qty = (pos.quantity // self.lot_size) * self.lot_size

                    # If holding less than one lot, allow full clear (though buy restricted to lots)
                    if sell_qty == 0 and pos.quantity > 0:
                        sell_qty = pos.quantity # Close dust
                    
                    if sell_qty > 0:
                         self.broker.sell(date, symbol, close_price, sell_qty)

                if sell_qty == 0 and pos is not None:
                    if pos.quantity > 0:
                        sell_qty = pos.quantity
                        logger.info(f"[{date}] Holding less than one lot ({pos.quantity}), will sell entire holding.")
                    else:
                        logger.info(f"[{date}] No shares to sell for {symbol}.")

                if sell_qty is not None and sell_qty > 0 and pos is not None:
                    logger.info(f"[{date}] Executing sell: symbol={symbol}, quantity={sell_qty}, price={close_price:.2f}")
                    self.broker.sell(date, symbol, close_price, sell_qty)