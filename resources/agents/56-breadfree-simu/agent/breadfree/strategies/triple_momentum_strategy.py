from .base_strategy import BreadFreeStrategy
import pandas as pd
import numpy as np
from scipy import stats
from ..utils.logger import get_logger

logger = get_logger(__name__)

class TripleMomentumStrategy(BreadFreeStrategy):
    def __init__(self, broker, 
                 bias_n=24, 
                 momentum_day=25, 
                 slope_n=20, 
                 hold_period=20, 
                 lot_size=100, 
                 rebalance_threshold=1.5, **kwargs):
        """
        三因子动量策略 (Triple Momentum Strategy)
        结合乖离动量、斜率动量、效率动量三个因子进行轮动
        
        :param broker: Broker对象
        :param bias_n: 乖离率的均线窗口 (BIAS_N)
        :param momentum_day: 乖离率回归的计算窗口 (MOMENTUM_DAY)
        :param slope_n: 斜率动量和效率动量的计算窗口 (SLOPE_N)
        :param hold_period: 调仓周期
        :param lot_size: 最小交易单位
        :param rebalance_threshold: 调仓阈值 (新标的得分需超过原标的得分的倍数)
        """
        super().__init__(broker, lot_size=lot_size)
        self.bias_n = bias_n
        self.momentum_day = momentum_day
        self.slope_n = slope_n
        self.hold_period = hold_period
        self.rebalance_threshold = rebalance_threshold
        
        self.days_counter = 0
        self.ohlc_history = {}  # {symbol: [dict]}
        self.last_valid_ohlc = {} # {symbol: dict}
        self.trade_counter = 0

    def preload_history(self, history_map):
        """Preload history with full OHLC data"""
        for symbol, df in history_map.items():
            if not df.empty:
                records = df[['open', 'high', 'low', 'close']].to_dict('records')
                self.ohlc_history[symbol] = records
                if records:
                    self.last_valid_ohlc[symbol] = records[-1]
                # Also maintain base history just in case
                self.history[symbol] = df['close'].tolist()

    def on_bar(self, date, bars):
        # 1. Update data
        self.update_history(bars)
        
        self.days_counter += 1
        
        # 2. Check rebalance
        if self.days_counter % self.hold_period != 0:
            return

        # 3. Rebalance
        self.rebalance(date, bars)

    def update_history(self, bars):
        """Update historical data handling suspensions"""
        for symbol in self.symbols:
            if symbol in bars:
                bar = bars[symbol]
                record = {
                    'open': bar['open'], 
                    'high': bar['high'], 
                    'low': bar['low'], 
                    'close': bar['close']
                }
                if symbol not in self.ohlc_history:
                    self.ohlc_history[symbol] = []
                self.ohlc_history[symbol].append(record)
                self.last_valid_ohlc[symbol] = record
                
                # Base history sync
                if symbol not in self.history: self.history[symbol] = []
                self.history[symbol].append(bar['close'])
            else:
                # Suspension handling: forward fill
                if symbol in self.last_valid_ohlc:
                    fill_record = self.last_valid_ohlc[symbol]
                    self.ohlc_history[symbol].append(fill_record)
                    self.history[symbol].append(fill_record['close'])

    # --- Factor Calculations ---

    def _get_bias_factor(self, closes):
        """
        乖离动量因子
        1. 计算BIAS_N日均线乖离率
        2. 取最近MOMENTUM_DAY天乖离率做线性回归
        """
        required_len = self.bias_n + self.momentum_day
        if len(closes) < required_len:
            return None
            
        s_close = pd.Series(closes)
        # 乖离率 = 价格 / N日均线
        ma = s_close.rolling(window=self.bias_n, min_periods=1).mean()
        bias = s_close / ma
        
        # 取最近MOMENTUM_DAY天
        bias_recent = bias.iloc[-self.momentum_day:]
        
        # 归一化：除以起初值 (Logic from prompt: bias_recent / bias_recent.iloc[0])
        if bias_recent.iloc[0] == 0: return 0 # Prevent div by zero
        y = (bias_recent / bias_recent.iloc[0]).values
        x = np.arange(len(y))
        
        # 线性回归
        try:
            slope, _, _, _, _ = stats.linregress(x, y)
            return slope * 10000
        except:
            return 0

    def _get_slope_factor(self, closes):
        """
        斜率动量因子
        1. 价格标准化
        2. 计算SLOPE_N日回归斜率和R2
        """
        if len(closes) < self.slope_n:
            return None
        
        recent = np.array(closes[-self.slope_n:])
        if recent[0] == 0: return 0
        
        # 价格标准化
        normalized = recent / recent[0]
        x = np.arange(1, len(recent) + 1)
        y = normalized
        
        try:
            slope, _, r_value, _, _ = stats.linregress(x, y)
            r2 = r_value ** 2
            return 10000 * slope * r2
        except:
            return 0

    def _get_efficiency_factor(self, df):
        """
        效率动量因子
        1. 计算今日中枢价 Pivot
        2. 计算Momentum和Efficiency Ratio
        """
        if len(df) < self.slope_n:
            return None
            
        subset = df.iloc[-self.slope_n:].copy()
        subset['pivot'] = (subset['open'] + subset['high'] + subset['low'] + subset['close']) / 4.0
        
        if subset['pivot'].min() <= 0: return 0 # Log safety
        
        # 动量: 对数收益率
        momentum = 100 * np.log(subset['pivot'].iloc[-1] / subset['pivot'].iloc[0])
        
        # 效率系数: 净移动距离 / 总波动
        # Direction = abs(log(last) - log(first))
        log_pivot = np.log(subset['pivot'])
        direction = abs(log_pivot.iloc[-1] - log_pivot.iloc[0])
        volatility = log_pivot.diff().abs().sum()
        
        efficiency_ratio = direction / volatility if volatility > 1e-6 else 0
        
        return momentum * efficiency_ratio

    def rebalance(self, date, bars):
        # 1. 计算所有Valid Symbol的因子
        factor_data = []
        
        for symbol in self.symbols:
            if symbol not in self.ohlc_history:
                continue
                
            hist_records = self.ohlc_history[symbol]
            if len(hist_records) < max(self.bias_n + self.momentum_day, self.slope_n):
                continue
            
            # Prepare data
            closes = [r['close'] for r in hist_records]
            # Use dataframe for efficient processing in _get_efficiency_factor if needed, 
            # here we construct a mini DF for efficiency factor specifically
            df_hist = pd.DataFrame(hist_records)
            
            b_score = self._get_bias_factor(closes)
            s_score = self._get_slope_factor(closes)
            e_score = self._get_efficiency_factor(df_hist)
            
            if b_score is not None and s_score is not None and e_score is not None:
                factor_data.append({
                    'symbol': symbol,
                    'bias': b_score,
                    'slope': s_score,
                    'efficiency': e_score
                })
        
        if not factor_data:
            logger.info("Not enough data for any symbol.")
            return

        # 2. Z-Score 标准化与融合
        df_scores = pd.DataFrame(factor_data).set_index('symbol')
        
        # Z-Score标准化: (x - mean) / std
        # 注意: std可能为0(如只有一个标的), fillna(0)
        stds = df_scores.std()
        means = df_scores.mean()
        
        # Handle zero std
        stds = stds.replace(0, 1)
        
        z_scores = (df_scores - means) / stds
        z_scores['total'] = z_scores.sum(axis=1) # 简单的等权相加
        
        # 3. 排序
        ranked = z_scores.sort_values('total', ascending=False)
        
        logger.info(f"\n{date} Rebalance - Top Candidates:\n{ranked[['total']].head(5)}")

        # 4. 调仓阈值逻辑 (主要针对Top 1)
        target_symbol = None
        
        # 获取当前最强
        if not ranked.empty:
            best_symbol = ranked.index[0]
            best_score = ranked.iloc[0]['total']
            
            # 检查当前持仓
            current_positions = list(self.broker.positions.keys())
            held_symbol = current_positions[0] if current_positions else None
            
            target_symbol = best_symbol # 默认切换到最强
            
            if held_symbol:
                if held_symbol not in ranked.index:
                    # 持仓已不在候选池(可能数据不够或被剔除)，直接切换
                    logger.info(f"held symbol {held_symbol} not in candidates, switching.")
                    target_symbol = best_symbol
                elif held_symbol == best_symbol:
                    # 持仓就是第一名，保持
                    target_symbol = held_symbol
                else:
                    # 持仓不是第一名，判断阈值
                    current_score = ranked.loc[held_symbol, 'total']
                    
                    # 阈值逻辑: New > Old * 1.5
                    # 注意: Z-Score可能为负。
                    # 如果 Old < 0 且 New > Old * 1.5 (负数变小)，这逻辑会有问题。
                    # 但按照用户描述 "第一名的评分基础上，再乘以1.5", 严格执行之
                    
                    if best_score > current_score * self.rebalance_threshold:
                         logger.info(f"Switch triggered: {best_symbol}({best_score:.2f}) > {held_symbol}({current_score:.2f}) * {self.rebalance_threshold}")
                         target_symbol = best_symbol
                    else:
                         logger.info(f"Keep holding {held_symbol}({current_score:.2f}). Best {best_symbol}({best_score:.2f}) didn't beat thresh.")
                         target_symbol = held_symbol
        
        # 5. 执行交易
        if target_symbol:
            # Sell others
            current_positions = list(self.broker.positions.keys())
            for s in current_positions:
                if s != target_symbol:
                    if s in bars:
                        self.broker.sell(date, s, bars[s]['close'], self.broker.positions[s].quantity)
            
            # Buy target
            if target_symbol not in self.broker.positions:
                if target_symbol in bars:
                    available_cash = self.broker.cash
                    price = bars[target_symbol]['close']
                    # 考虑预留一点给手续费
                    qty = int(available_cash / (price * (1+self.broker.commission_rate)) // self.lot_size) * self.lot_size
                    
                    if qty > 0:
                        self.broker.buy(date, target_symbol, price, qty)
