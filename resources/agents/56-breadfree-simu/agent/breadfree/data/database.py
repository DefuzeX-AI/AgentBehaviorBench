"""
Database Management Module - For storing market data (Stocks, ETFs) and technical indicators
"""

import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import models & metrics
from .db_models import (
    Base, StockInfo, DailyData, MonthlyData, 
    TechnicalIndicators, SectorInfo, StockSectorMapping, SentimentData
)
from breadfree.utils.metrics import calculate_ema, calculate_macd

class DatabaseManager:
    """Database management class"""

    def __init__(self, is_del: bool = False, db_path: str = "breadfree.db"):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        self.Session = sessionmaker(bind=self.engine)
        if is_del:
            self.del_tables()
        # Create database tables
        self.create_tables()

    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(self.engine)

    def del_tables(self):
        """Delete all tables"""
        Base.metadata.drop_all(self.engine)

    def init_from_csv(self, csv_path: str):
        """Initialize stock info from CSV file"""
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')

            session = self.Session()

            for _, row in df.iterrows():
                # Map column names (English preferred)
                symbol = str(row.get('symbol', row.get('代码', ''))).zfill(6)
                name = row.get('name', row.get('名称', ''))
                circ_mv = row.get('circ_mv', row.get('流通市值', 0))
                industry = row.get('industry', row.get('行业板块', ''))
                concept = row.get('concept', row.get('概念板块', ''))

                # Handle potential NaN values
                industry = str(industry) if pd.notna(industry) else ''
                concept = str(concept) if pd.notna(concept) else ''

                # Check if already exists
                existing = session.query(StockInfo).filter_by(symbol=symbol).first()
                if not existing:
                    stock = StockInfo(
                        symbol=symbol,
                        name=name,
                        circ_mv=circ_mv,
                        industry=industry,
                        concept=concept
                    )
                    session.add(stock)

                    # Add sector mapping
                    if industry:
                        sector_mapping = StockSectorMapping(
                            symbol=symbol,
                            sector_type='industry',
                            sector_name=industry
                        )
                        session.add(sector_mapping)

                    if concept:
                        concept_list = [c.strip() for c in concept.split(',') if c.strip()]
                        for concept_name in concept_list:
                            sector_mapping = StockSectorMapping(
                                symbol=symbol,
                                sector_type='concept',
                                sector_name=concept_name
                            )
                            session.add(sector_mapping)

            session.commit()
            session.close()
            print(f"Successfully imported {len(df)} stock info records")

        except Exception as e:
            print(f"Failed to import CSV data: {e}")

    def store_daily_data(self, symbol: str, data: pd.DataFrame):
        """Store daily data for any symbol (Stock or ETF)"""
        if data.empty:
            return

        # Ensure 'date' is a column for iteration if it was set as index
        df_to_store = data.reset_index() if 'date' not in data.columns else data.copy()
        session = self.Session()

        try:
            for _, row in df_to_store.iterrows():
                # Check if already exists
                trade_date = pd.to_datetime(row['date']).date()
                existing = session.query(DailyData).filter_by(
                    symbol=symbol,
                    trade_date=trade_date
                ).first()

                if not existing:
                    daily_data = DailyData(
                        symbol=symbol,
                        trade_date=trade_date,
                        open=row.get('open'),
                        close=row.get('close'),
                        high=row.get('high'),
                        low=row.get('low'),
                        volume=row.get('volume'),
                        amount=row.get('amount'),
                        amplitude=row.get('amplitude'),
                        pct_chg=row.get('pct_chg'),
                        change=row.get('change'),
                        turnover=row.get('turnover')
                    )
                    session.add(daily_data)

            session.commit()
            print(f"Successfully stored {len(data)} daily records for {symbol}")

        except Exception as e:
            session.rollback()
            print(f"Failed to store daily data: {e}")
        finally:
            session.close()

    def calculate_technical_indicators(self, symbol: str):
        """Calculate and store technical indicators"""
        session = self.Session()

        try:
            # Get daily data
            query = session.query(DailyData).filter_by(symbol=symbol).order_by(DailyData.trade_date)
            df = pd.read_sql(query.statement, session.bind)

            if len(df) < 30:  # Insufficient data
                return

            # Calculate various EMAs
            df['ema_5'] = calculate_ema(df['close'], 5)
            df['ema_10'] = calculate_ema(df['close'], 10)
            df['ema_20'] = calculate_ema(df['close'], 20)
            df['ema_30'] = calculate_ema(df['close'], 30)
            df['ema_60'] = calculate_ema(df['close'], 60)
            df['ema_120'] = calculate_ema(df['close'], 120)

            # Calculate MACD
            df['macd'], df['macd_signal'], df['macd_histogram'] = calculate_macd(df['close'])

            # Store technical indicators
            for _, row in df.iterrows():
                existing = session.query(TechnicalIndicators).filter_by(
                    symbol=symbol,
                    trade_date=row['trade_date']
                ).first()

                if not existing:
                    indicator = TechnicalIndicators(
                        symbol=symbol,
                        trade_date=row['trade_date'],
                        ema_5=row.get('ema_5'),
                        ema_10=row.get('ema_10'),
                        ema_20=row.get('ema_20'),
                        ema_30=row.get('ema_30'),
                        ema_60=row.get('ema_60'),
                        ema_120=row.get('ema_120'),
                        macd=row.get('macd'),
                        macd_signal=row.get('macd_signal'),
                        macd_histogram=row.get('macd_histogram')
                    )
                    session.add(indicator)

            session.commit()
            print(f"Successfully calculated and stored technical indicators for {symbol}")

        except Exception as e:
            session.rollback()
            print(f"Failed to calculate technical indicators: {e}")
        finally:
            session.close()

    def generate_monthly_data(self, symbol: str):
        """Generate monthly data from daily data"""
        session = self.Session()

        try:
            # Get daily data
            query = session.query(DailyData).filter_by(symbol=symbol).order_by(DailyData.trade_date)
            daily_df = pd.read_sql(query.statement, session.bind)

            if len(daily_df) == 0:
                return

            # Convert to monthly data
            daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date'])
            daily_df.set_index('trade_date', inplace=True)

            # Aggregate by month (Note: 'ME' is month-end in modern pandas)
            monthly_df = daily_df.resample('ME').agg({
                'open': 'first',
                'close': 'last',
                'high': 'max',
                'low': 'min',
                'volume': 'sum',
                'amount': 'sum'
            }).dropna()

            # Calculate monthly percentage change
            monthly_df['pct_chg'] = monthly_df['close'].pct_change() * 100

            # Calculate monthly technical indicators
            monthly_df['ema_12'] = calculate_ema(monthly_df['close'], 12)
            monthly_df['ema_26'] = calculate_ema(monthly_df['close'], 26)
            monthly_df['macd'], monthly_df['macd_signal'], monthly_df['macd_histogram'] = calculate_macd(monthly_df['close'])

            # Store monthly data
            for date, row in monthly_df.iterrows():
                existing = session.query(MonthlyData).filter_by(
                    symbol=symbol,
                    trade_date=date
                ).first()

                if not existing:
                    monthly_data = MonthlyData(
                        symbol=symbol,
                        trade_date=date,
                        open=row.get('open'),
                        close=row.get('close'),
                        high=row.get('high'),
                        low=row.get('low'),
                        volume=row.get('volume'),
                        amount=row.get('amount'),
                        pct_chg=row.get('pct_chg'),
                        ema_12=row.get('ema_12'),
                        ema_26=row.get('ema_26'),
                        macd=row.get('macd'),
                        macd_signal=row.get('macd_signal'),
                        macd_histogram=row.get('macd_histogram')
                    )
                    session.add(monthly_data)

            session.commit()
            print(f"Successfully generated {len(monthly_df)} monthly records for {symbol}")

        except Exception as e:
            session.rollback()
            print(f"Failed to generate monthly data: {e}")
        finally:
            session.close()

    def get_stock_list(self) -> List[str]:
        """Get list of stock symbols"""
        session = self.Session()
        try:
            stocks = session.query(StockInfo.symbol).all()
            return [stock[0] for stock in stocks]
        finally:
            session.close()

    def get_daily_data(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """Get daily data for a specific symbol"""
        session = self.Session()
        try:
            query = session.query(DailyData).filter_by(symbol=symbol)

            if start_date:
                query = query.filter(DailyData.trade_date >= pd.to_datetime(start_date))
            if end_date:
                query = query.filter(DailyData.trade_date <= pd.to_datetime(end_date))

            query = query.order_by(DailyData.trade_date)
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()

    def get_technical_indicators(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """Get technical indicator data for a specific symbol"""
        session = self.Session()
        try:
            query = session.query(TechnicalIndicators).filter_by(symbol=symbol)

            if start_date:
                query = query.filter(TechnicalIndicators.trade_date >= pd.to_datetime(start_date))
            if end_date:
                query = query.filter(TechnicalIndicators.trade_date <= pd.to_datetime(end_date))

            query = query.order_by(TechnicalIndicators.trade_date)
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()

# Singleton pattern
db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager

if __name__ == "__main__":
    # Test database functionality
    db = DatabaseManager()

    # Initialize stock info
    csv_path = "breadfree/data/top_150_with_sectors.csv"
    if os.path.exists(csv_path):
        db.init_from_csv(csv_path)

    print("Database initialization complete")