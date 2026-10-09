from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

# SQLAlchemy base class
Base = declarative_base()

class StockInfo(Base):
    """Asset basic information table (Supports Stocks and ETFs)"""
    __tablename__ = 'stock_info'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    market = Column(String(10))
    industry = Column(String(50))  # Industry sector or ETF category
    concept = Column(String(200))  # Concept sector or ETF theme
    circ_mv = Column(Float)  # Circulating market value
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class DailyData(Base):
    """Daily data table for all symbols (Stocks, ETFs, Indices)"""
    __tablename__ = 'daily_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    amplitude = Column(Float)  # Amplitude
    pct_chg = Column(Float)    # Percentage change
    change = Column(Float)     # Change amount
    turnover = Column(Float)   # Turnover rate

    # Unique constraint: symbol + trade date
    __table_args__ = (UniqueConstraint('symbol', 'trade_date', name='uq_symbol_date'),)

class MonthlyData(Base):
    """Monthly data table"""
    __tablename__ = 'monthly_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)  # Month end date
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    pct_chg = Column(Float)    # Monthly percentage change

    # Technical indicators
    ema_12 = Column(Float)     # 12-day EMA
    ema_26 = Column(Float)     # 26-day EMA
    macd = Column(Float)       # MACD
    macd_signal = Column(Float)  # MACD signal line
    macd_histogram = Column(Float)  # MACD histogram

    __table_args__ = (UniqueConstraint('symbol', 'trade_date', name='uq_monthly_symbol_date'),)

class TechnicalIndicators(Base):
    """Technical indicators table"""
    __tablename__ = 'technical_indicators'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)

    # EMA indicators
    ema_5 = Column(Float)      # 5-day EMA
    ema_10 = Column(Float)     # 10-day EMA
    ema_20 = Column(Float)     # 20-day EMA
    ema_30 = Column(Float)     # 30-day EMA
    ema_60 = Column(Float)     # 60-day EMA
    ema_120 = Column(Float)    # 120-day EMA

    # MACD indicators
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)

    # Other common indicators
    rsi = Column(Float)        # RSI
    kdj_k = Column(Float)      # KDJ-K
    kdj_d = Column(Float)      # KDJ-D
    kdj_j = Column(Float)      # KDJ-J
    boll_upper = Column(Float) # BOLL upper band
    boll_middle = Column(Float) # BOLL middle band
    boll_lower = Column(Float) # BOLL lower band

    __table_args__ = (UniqueConstraint('symbol', 'trade_date', name='uq_tech_symbol_date'),)

class SectorInfo(Base):
    """Sector information table"""
    __tablename__ = 'sector_info'

    id = Column(Integer, primary_key=True)
    sector_type = Column(String(20), nullable=False)  # 'industry' or 'concept'
    sector_name = Column(String(50), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint('sector_type', 'sector_name', name='uq_sector_type_name'),)

class StockSectorMapping(Base):
    """Stock-Sector mapping table"""
    __tablename__ = 'stock_sector_mapping'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    sector_type = Column(String(20), nullable=False)
    sector_name = Column(String(50), nullable=False)

    __table_args__ = (UniqueConstraint('symbol', 'sector_type', 'sector_name', name='uq_symbol_sector'),)

class SentimentData(Base):
    """Sentiment data table (Reserved)"""
    __tablename__ = 'sentiment_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    news_date = Column(Date, nullable=False, index=True)
    sentiment_score = Column(Float)  # Sentiment score
    news_count = Column(Integer)     # Number of news items
    keywords = Column(Text)          # Keywords
    source = Column(String(50))      # Data source
    created_at = Column(DateTime, default=datetime.now)
