from .base_strategy import BreadFreeStrategy

class BenchmarkStrategy(BreadFreeStrategy):
    """
    Market Benchmark Strategy (Buy and Hold)
    Simply buys the asset on the first available opportunity and holds it until the end.
    Used as a baseline to compare other strategies against the market performance.
    """
    def __init__(self, broker, lot_size=100, **kwargs):
        super().__init__(broker, lot_size)
        self.params = kwargs
        self.invested = {} # {symbol: bool}

    def set_symbols(self, symbols):
        super().set_symbols(symbols)
        self.invested = {s: False for s in symbols}

    def on_bar(self, date, bars):
        # Buy on the first day available for each symbol
        available_cash = self.broker.cash
        # Strategy: Buy everything on start, equal weighting?
        # Or Just fill up.
        # For simple benchmarking, we just try to buy 'target allocation' for each symbol once.
        
        target_per_symbol = self.broker.initial_cash / len(self.symbols)

        for symbol, bar_data in bars.items():
            if self.invested.get(symbol, False):
                continue

            close_price = bar_data['close']
            
            # Simple check if we have enough cash (ignoring that other symbols might need cash too)
            # In a real portfolio construction we would allocate strictly. 
            # Here: Try to buy 1/N value.
            
            # Estimate max shares for this chunk
            max_shares = int(target_per_symbol / (close_price * (1 + self.broker.commission_rate)))
            quantity = (max_shares // self.lot_size) * self.lot_size
            
            if quantity > 0:
                 # Check actual cash availability (since other buys might have drained it if logic is loose)
                 cost = quantity * close_price * (1 + self.broker.commission_rate)
                 if self.broker.cash >= cost:
                      print(f"[{date}] Benchmark Buy: Buying {quantity} shares of {symbol} at {close_price:.2f}")
                      self.broker.buy(date, symbol, close_price, quantity)
                      self.invested[symbol] = True
                 else:
                      print(f"[{date}] Insufficient cash for benchmark buy of {symbol}. Needed: {cost:.2f}, Has: {self.broker.cash:.2f}")
