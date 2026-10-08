class Position:
    def __init__(self, symbol, quantity, avg_price):
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        # 记录持仓的买入日期，用于简单的先进先出(FIFO)或平均成本匹配。
        # 简化版 Broker 使用平均成本，不追踪具体的 tax lots。
        
    def __repr__(self):
        return f"Position({self.symbol}, {self.quantity}, {self.avg_price:.2f})"

class Broker:
    def __init__(self, initial_cash=100000.0, commission_rate=0.0003):
        self.initial_cash = initial_cash # 初始资金
        self.cash = initial_cash # 当前可用资金
        self.positions = {} # symbol -> Position
        self.commission_rate = commission_rate
        self.transaction_history = []
        self.equity_curve = [] # 记录每日权益变化
        self.current_equity = initial_cash # 当前总权益（现金 + 持仓市值）
        # 新增：记录已平仓的交易盈亏，用于计算胜率
        self.closed_trades = [] # List of {'symbol', 'buy_date', 'sell_date', 'buy_price', 'sell_price', 'quantity', 'pnl', 'return_pct'}

    def buy(self, date, symbol, price, quantity):
        cost = price * quantity
        commission = cost * self.commission_rate
        total_cost = cost + commission

        if self.cash >= total_cost:
            self.cash -= total_cost
            if symbol in self.positions:
                pos = self.positions[symbol]
                new_quantity = pos.quantity + quantity
                # Weighted average price
                new_avg_price = (pos.quantity * pos.avg_price + cost) / new_quantity
                pos.quantity = new_quantity
                pos.avg_price = new_avg_price
            else:
                self.positions[symbol] = Position(symbol, quantity, price)
            
            self.transaction_history.append({
                'date': date,
                'action': 'BUY',
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'commission': commission,
                'cash_remaining': self.cash
            })
            self.current_equity = self.get_total_equity({symbol: price})
            return True
        else:
            print(f"[{date}] Insufficient cash to buy {symbol}. Needed: {total_cost:.2f}, Available: {self.cash:.2f}")
            return False

    def sell(self, date, symbol, price, quantity):
        if symbol in self.positions and self.positions[symbol].quantity >= quantity:
            revenue = price * quantity
            commission = revenue * self.commission_rate
            net_revenue = revenue - commission
            
            # 记录交易盈亏 (基于平均成本法)
            pos = self.positions[symbol]
            buy_price = pos.avg_price
            pnl = (price - buy_price) * quantity - commission # 这里的 PnL 只扣除了卖出佣金，买入佣金已隐含在 cash 变动，但通常计算 PnL 应该包含双边？
            # 实际上 pos.avg_price 通常不包含佣金成本，如果 Broker.buy 也没把佣金加进 avg_price 的话。
            # 检查 Broker.buy: total_cost 计算了佣金，但 pos.avg_price = (old * old_p + cost) / new_q，这里的 cost = price * quantity，没加佣金。
            # 所以 avg_price 是纯价格。
            
            # 更精确的 PnL: (Sell Price - Buy Price) * Qty - Sell Commission - (Buy Commission approximation)
            # 简化近似：
            trade_return_pct = (price - buy_price) / buy_price
            
            self.closed_trades.append({
                'symbol': symbol,
                'sell_date': date,
                'buy_price': buy_price,
                'sell_price': price,
                'quantity': quantity,
                'pnl': pnl, # Net PnL (approx)
                'return_pct': trade_return_pct
            })

            self.cash += net_revenue
            pos.quantity -= quantity
            
            if pos.quantity == 0:
                del self.positions[symbol]
            
            self.transaction_history.append({
                'date': date,
                'action': 'SELL',
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'commission': commission,
                'cash_remaining': self.cash
            })
            self.current_equity = self.get_total_equity({symbol: price})
            return True
        else:
            print(f"[{date}] Insufficient positions to sell {symbol}.")
            return False

    def get_total_equity(self, current_prices):
        """
        Calculate total equity (Cash + Market Value of Positions)
        :param current_prices: dict {symbol: price}
        """
        market_value = 0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos.avg_price) # Use last known price if current not available
            market_value += pos.quantity * price
        return self.cash + market_value