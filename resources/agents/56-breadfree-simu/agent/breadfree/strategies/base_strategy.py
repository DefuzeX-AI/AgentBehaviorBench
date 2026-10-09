from ..utils.logger import get_logger

logger = get_logger(__name__)

class BreadFreeStrategy:
    def __init__(self, broker, lot_size=100):
        self.broker = broker
        self.lot_size = lot_size
        self.symbols = []
        self.history = {}  # {symbol: [close_prices]}

    def set_symbols(self, symbols):
        """
        Set the symbols for the strategy and initialize history storage.
        Can be overridden by subclasses if extra initialization is needed.
        """
        self.symbols = symbols
        for s in symbols:
            if s not in self.history:
                self.history[s] = []

    def preload_history(self, history_map):
        """
        Preload history for calculation.
        :param history_map: {symbol: DataFrame}
        """
        for symbol, df in history_map.items():
            if not df.empty and 'close' in df.columns:
                # Moving average and other indicator calculations typically only need Close
                self.history[symbol] = df['close'].tolist()
                logger.info(f"{self.__class__.__name__}: Preloaded {len(self.history[symbol])} days of history for {symbol}.")

    def on_bar(self, date, bars):
        """
        Called on every step (day)
        :param date: current date
        :param bars: dict {symbol: bar_data}, where bar_data is a dict or Series containing Open, High, Low, Close, Volume
        """
        raise NotImplementedError
