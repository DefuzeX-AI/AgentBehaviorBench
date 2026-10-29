#!/usr/bin/env python3
"""
Database Initialization Script - One-click initialization and data import
"""

import os
import sys
from breadfree.data.database import DatabaseManager
from breadfree.data.data_importer import DataImporter

def main():
    """Main initialization function"""
    print("=" * 50)
    print("BreadFree Database Initialization Tool")
    print("=" * 50)

    # Check dependency files
    csv_path = "breadfree/data/cache/top_150_with_sectors.csv"
    cache_dir = "breadfree/data/cache"

    if not os.path.exists(csv_path):
        print(f"❌ Stock info file not found: {csv_path}")
        sys.exit(1)

    if not os.path.exists(cache_dir):
        print(f"❌ Cache directory not found: {cache_dir}")
        sys.exit(1)

    print("✅ Dependency check passed")

    # Create database manager
    print("\nCreating database...")
    db_manager = DatabaseManager(is_del=True) # is_del=True

    # Create data importer
    importer = DataImporter(db_manager)

    # Initialize stock information
    print("\nInitializing stock information from CSV...")
    db_manager.init_from_csv(csv_path)
    print("✅ Stock info initialization complete")
    # Import cache data
    print("\nImporting cached data into database...")
    importer.import_cache_data()
    print("✅ Data import complete")

    # Show final status
    status = importer.get_import_status()
    print("\n" + "=" * 50)
    print("🎉 Database initialization complete!")
    print("=" * 50)
    print(f"📊 Stock count: {status['stock_count']}")
    print(f"📈 Daily records: {status['daily_records']}")
    print(f"📅 Monthly records: {status['monthly_records']}")
    print(f"📊 Technical indicators: {status['indicator_records']}")
    print(f"🕒 Update time: {status['last_update']}")
    print("\nDatabase file: breadfree.db")
    print("=" * 50)

    # Get stock list
    stocks = db_manager.get_stock_list()
    print(f"Number of stocks: {len(stocks)}")

    # Get daily data for a specific stock
    data = db_manager.get_daily_data('601288', start_date='2024-01-01', end_date='2024-12-31')
    print(f"Daily records for 601288: {len(data)}")

    # Get technical indicators
    indicators = db_manager.get_technical_indicators('601288', start_date='2024-01-01')
    print(f"Indicator records for 601288: {len(indicators)}")


if __name__ == "__main__":
    main()