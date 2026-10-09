from .base_strategy import BreadFreeStrategy
import pandas as pd
import numpy as np
from scipy import stats
from ..utils.logger import get_logger
from collections import defaultdict

logger = get_logger(__name__)

class RotationStrategy(BreadFreeStrategy):
    def __init__(self, broker, lookback_period=20, hold_period=20, top_n=2,
                 use_efficiency=True, lot_size=100, min_data_ratio=1.5,
                 enable_dynamic_weight=False, min_momentum=0.0):
        """
        Enhanced ETF Efficiency Rotation Strategy
        :param broker: Broker instance
        :param lookback_period: Lookback period (days)
        :param hold_period: Holding period (days)
        :param top_n: Number of top ETFs to hold
        :param use_efficiency: True -> Efficiency rotation; False -> Pure momentum rotation
        :param lot_size: Minimum trading unit
        :param min_data_ratio: Minimum data ratio relative to lookback_period
        :param enable_dynamic_weight: Enable dynamic weight allocation
        :param min_momentum: Momentum threshold (0 means no filtering)
        """
        super().__init__(broker, lot_size=lot_size)
        self.lookback_period = lookback_period
        self.hold_period = hold_period
        self.top_n = top_n
        self.use_efficiency = use_efficiency
        self.min_data_ratio = min_data_ratio
        self.min_data_length = max(int(lookback_period * min_data_ratio), 30)
        self.enable_dynamic_weight = enable_dynamic_weight
        self.min_momentum = min_momentum
        
        # Enhanced data structures
        self.days_counter = 0
        self.suspension_flags = defaultdict(bool)
        self.last_valid_prices = {}
        
        # Performance monitoring
        self.trade_counter = 0
        self.rebalance_dates = []

    def stable_linear_regression(self, prices):
        """Robust linear regression calculation with outlier handling"""
        n = len(prices)
        if n < 2:
            return 0.0, 0.0, 0.0  # slope, intercept, r2
        
        try:
            x = np.arange(n)
            slope, intercept, r_value, _, _ = stats.linregress(x, prices)
            r2 = r_value ** 2
            return slope, intercept, r2
        except:
            # Fallback to simple method if regression fails
            price_diff = prices[-1] - prices[0]
            return price_diff / max(n-1, 1), prices[0], 0.0

    def calculate_efficiency_score(self, symbol, window):
        """
        Calculate efficiency score: (Momentum / Volatility) * R^2 (Trend Stability)
        Uses vectorized calculation for performance.
        """
        history = self.history[symbol]
        
        # Data length check
        if len(history) < self.min_data_length:
            logger.debug(f"Insufficient data: {symbol} ({len(history)} < {self.min_data_length})")
            return -np.inf
            
        # Get window data
        start_idx = max(0, len(history) - window)
        prices = np.array(history[start_idx:])
        
        # 1. Momentum (ROC)
        momentum = (prices[-1] / prices[0] - 1) if prices[0] > 0 else 0
        
        # Return early for pure momentum mode
        if not self.use_efficiency:
            return momentum
            
        try:
            # 2. Volatility (Std of returns)
            returns = np.diff(prices) / prices[:-1]
            volatility = np.std(returns) if len(returns) > 1 else 0
            
            # 3. Trend Stability (R^2)
            _, _, r2 = self.stable_linear_regression(prices)
            
            # 4. Efficiency score calculation
            epsilon = 1e-6
            efficiency = (momentum / (volatility + epsilon)) * max(r2, 0)
            return efficiency
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return -np.inf

    def update_suspension_status(self, date, bars):
        """Update suspension status and fill historical prices"""
        for symbol in self.symbols:
            # Detect suspension: no data today but had data previously
            if symbol not in bars and symbol in self.last_valid_prices:
                self.suspension_flags[symbol] = True
                last_price = self.last_valid_prices[symbol]
                self.history[symbol].append(last_price)
                logger.debug(f"{date} {symbol} suspended, using previous price: {last_price}")
            elif symbol in bars:
                price = bars[symbol]['close']
                self.history[symbol].append(price)
                self.last_valid_prices[symbol] = price
                self.suspension_flags[symbol] = False
            else:
                # New listing or long-term suspension
                if symbol not in self.history or not self.history[symbol]:
                    self.history[symbol] = []

    def filter_valid_symbols(self):
        """Filter valid symbols for trading"""
        valid_symbols = []
        for symbol in self.symbols:
            # Exclude suspended or insufficient data
            if self.suspension_flags.get(symbol, False):
                continue
                
            # Check data length
            if len(self.history.get(symbol, [])) < self.min_data_length:
                continue
                
            valid_symbols.append(symbol)
            
        return valid_symbols

    def calculate_weights(self, scores, symbols):
        """Calculate dynamic weight allocation"""
        if not self.enable_dynamic_weight or len(symbols) == 0:
            # Equal weight allocation
            return {s: 1.0/len(symbols) for s in symbols}
            
        # Score-based allocation (softmax)
        score_values = np.array([scores[s] for s in symbols])
        exp_scores = np.exp(score_values - np.max(score_values))
        weights = exp_scores / exp_scores.sum()
        return {s: w for s, w in zip(symbols, weights)}

    def execute_rebalancing(self, date, bars, target_symbols, scores):
        """Execute rebalancing trades"""
        # 1. Calculate total equity
        current_prices = {s: bars[s]['close'] for s in bars if s in self.history}
        total_equity = self.broker.get_total_equity(current_prices)
        
        # 2. Calculate target weights
        target_weights = self.calculate_weights(scores, target_symbols)
        logger.info(f"Target Weights: {target_weights}")
        
        # 3. Determine target values
        target_values = {s: total_equity * w for s, w in target_weights.items()}
        
        # 4. Sell non-target positions
        current_positions = list(self.broker.positions.keys())
        for symbol in current_positions:
            if symbol not in target_symbols and not self.suspension_flags.get(symbol, False):
                if symbol in bars:
                    pos = self.broker.positions[symbol]
                    if pos.quantity > 0:
                        self.broker.sell(date, symbol, bars[symbol]['close'], pos.quantity)
                        logger.info(f"Selling {symbol}: {pos.quantity} shares")
                        self.trade_counter += 1
                else:
                    logger.warning(f"Cannot sell {symbol} (Suspended?)")

        # 5. Buy/Adjust target positions
        for symbol in target_symbols:
            if symbol not in bars:
                logger.warning(f"Skipping buy for {symbol} (Suspended?)")
                continue
                
            price = bars[symbol]['close']
            target_value = target_values[symbol]
            
            # Current value
            current_value = 0
            if symbol in self.broker.positions:
                pos = self.broker.positions[symbol]
                current_value = pos.quantity * price
                
            # Difference to adjust
            value_diff = target_value - current_value
            
            # Buy logic
            if value_diff > 0:
                # Available cash considering commission
                available_cash = self.broker.cash
                max_buy_value = available_cash / (1 + self.broker.commission_rate)
                buy_value = min(value_diff, max_buy_value)
                
                # Calculate quantity with lot size
                buy_qty = int(buy_value // price)
                buy_qty = (buy_qty // self.lot_size) * self.lot_size
                
                if buy_qty > 0:
                    self.broker.buy(date, symbol, price, buy_qty)
                    logger.info(f"Buying {symbol}: {buy_qty} shares @ {price} (Target weight: {target_weights[symbol]:.2%})")
                    self.trade_counter += 1
            
            # Sell logic (reduction)
            elif value_diff < 0:
                sell_value = -value_diff
                sell_qty = int(sell_value // price)
                if symbol in self.broker.positions:
                    current_qty = self.broker.positions[symbol].quantity
                    sell_qty = min(sell_qty, current_qty)
                    sell_qty = (sell_qty // self.lot_size) * self.lot_size
                    
                    if sell_qty > 0:
                        self.broker.sell(date, symbol, price, sell_qty)
                        logger.info(f"Reducing position {symbol}: {sell_qty} shares (Target weight: {target_weights[symbol]:.2%})")
                        self.trade_counter += 1

    def on_bar(self, date, bars):
        # 1. Update data and handle suspensions
        self.update_suspension_status(date, bars)
        self.days_counter += 1
        
        # 2. Check rebalance day
        if self.days_counter % self.hold_period != 0:
            return
            
        self.rebalance_dates.append(date)
        strategy_name = 'Efficiency Rotation' if self.use_efficiency else 'Momentum Rotation'
        logger.info(f"\n{'='*50}\n{date} Rebalance Day ({strategy_name})")
        logger.info(f"Current Positions: {list(self.broker.positions.keys())}")
        
        # 3. Filter valid symbols
        valid_symbols = self.filter_valid_symbols()
        logger.info(f"Valid Symbols: {len(valid_symbols)}/{len(self.symbols)}")
        
        # 4. Calculate scores
        scores = {}
        for symbol in valid_symbols:
            scores[symbol] = self.calculate_efficiency_score(symbol, self.lookback_period)
        
        # 5. Filter target symbols
        # Remove invalid scores
        valid_scores = {k: v for k, v in scores.items() if v > -np.inf}
        
        # Sort by score
        sorted_symbols = sorted(valid_scores.keys(), key=lambda x: valid_scores[x], reverse=True)
        
        # Momentum threshold filtering
        if self.min_momentum > 0:
            target_symbols = [s for s in sorted_symbols[:self.top_n] 
                             if valid_scores[s] >= self.min_momentum]
            if len(target_symbols) < self.top_n:
                logger.info(f"Only {len(target_symbols)} symbols meet the momentum threshold")
        else:
            target_symbols = sorted_symbols[:self.top_n]
        
        logger.info(f"Target Positions: {target_symbols}")
        
        # 6. Execute rebalancing
        if target_symbols:
            self.execute_rebalancing(date, bars, target_symbols, scores)
        else:
            logger.info("No valid symbols found, holding cash")
            
        # Log post-rebalance status
        current_prices = {s: bars[s]['close'] for s in bars if s in self.history}
        logger.info(f"Equity after rebalance: {self.broker.get_total_equity(current_prices):.2f}")
        
    def get_performance_metrics(self):
        """Get strategy performance metrics"""
        return {
            'total_trades': self.trade_counter,
            'rebalance_count': len(self.rebalance_dates),
            'last_rebalance': self.rebalance_dates[-1] if self.rebalance_dates else None
        }
