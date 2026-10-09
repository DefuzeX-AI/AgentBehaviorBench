"""
Data Import Tool - Importing existing CSV cache data into the database
"""

import os
import pandas as pd
import glob
from datetime import datetime
from typing import List
from .database import DatabaseManager, StockInfo, DailyData, MonthlyData, TechnicalIndicators

class DataImporter:
    """Data importer utility class"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def import_cache_data(self, cache_dir: str = "breadfree/data/cache"):
        """Import all CSV data from the cache directory"""
        if not os.path.exists(cache_dir):
            print(f"Cache directory does not exist: {cache_dir}")
            return

        # Get all CSV files
        csv_files = glob.glob(os.path.join(cache_dir, "*.csv"))
        print(f"Found {len(csv_files)} CSV files")

        # Filter out qfq files (pre-adjusted data)
        qfq_files = [f for f in csv_files if '_qfq.csv' in f]
        regular_files = [f for f in csv_files if '_qfq.csv' not in f]

        print(f"Regular data files: {len(regular_files)}")
        print(f"Pre-adjusted data files: {len(qfq_files)}")

        # Import regular data first
        for file_path in regular_files:
            self.import_single_file(file_path)

        # Calculate technical indicators
        self.calculate_all_indicators()

    def import_single_file(self, file_path: str):
        """Import a single CSV file"""
        try:
            # Extract stock symbol from filename
            filename = os.path.basename(file_path)
            symbol = filename.split('_')[0]

            print(f"Importing data for {symbol}...")

            # Read CSV file
            df = pd.read_csv(file_path)

            # Check data columns
            if 'date' not in df.columns:
                print(f"File {filename} missing 'date' column, skipping")
                return

            # Store to database
            self.db_manager.store_daily_data(symbol, df)

            # Generate monthly data
            self.db_manager.generate_monthly_data(symbol)

            print(f"Successfully imported data for {symbol}")

        except Exception as e:
            print(f"Failed to import file {file_path}: {e}")

    def calculate_all_indicators(self):
        """Calculate technical indicators for all stocks"""
        stock_list = self.db_manager.get_stock_list()
        print(f"Starting indicator calculation for {len(stock_list)} stocks...")

        for symbol in stock_list:
            try:
                self.db_manager.calculate_technical_indicators(symbol)
                print(f"Completed indicator calculation for {symbol}")
            except Exception as e:
                print(f"Failed to calculate indicators for {symbol}: {e}")

    def get_import_status(self) -> dict:
        """Get import status statistics"""
        session = self.db_manager.Session()
        try:
            # Count records in each table
            stock_count = session.query(StockInfo).count()
            daily_count = session.query(DailyData).count()
            monthly_count = session.query(MonthlyData).count()
            indicator_count = session.query(TechnicalIndicators).count()

            return {
                'stock_count': stock_count,
                'daily_records': daily_count,
                'monthly_records': monthly_count,
                'indicator_records': indicator_count,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        finally:
            session.close()

def main():
    """Main function - Used to manually execute data import"""
    print("Starting data import...")

    # Create database manager
    db_manager = DatabaseManager()

    # Initialize stock information
    csv_path = "breadfree/data/top_150_with_sectors.csv"
    if os.path.exists(csv_path):
        db_manager.init_from_csv(csv_path)
        print("Stock info initialization complete")

    # Create data importer
    importer = DataImporter(db_manager)

    # Import cache data
    importer.import_cache_data()

    # Display import status
    status = importer.get_import_status()
    print("\nData import complete!")
    print(f"Stock count: {status['stock_count']}")
    print(f"Daily records: {status['daily_records']}")
    print(f"Monthly records: {status['monthly_records']}")
    print(f"Technical indicators: {status['indicator_records']}")
    print(f"Last update time: {status['last_update']}")

if __name__ == "__main__":
    main()