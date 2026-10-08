import akshare as ak
import pandas as pd
import time
import os

# Get real-time A-share market data (contains circulating market value)
stock_df = ak.stock_zh_a_spot_em()

# Sort by circulating market value descending
stock_df_sorted = stock_df.sort_values(by="流通市值", ascending=False)

# Extract top 150 stocks and rename keys to English
top_150 = stock_df_sorted.head(150)[["代码", "名称", "流通市值"]].copy()
top_150.columns = ["symbol", "name", "circ_mv"]

# Initialize new columns
top_150["industry"] = ""
top_150["concept"] = ""

for idx, row in top_150.iterrows():
    symbol = str(row["symbol"]).strip()
    if len(symbol) < 6:
        symbol = symbol.zfill(6)
    print(f"Fetching sector info for {symbol}")
    try:
        # Get individual stock info
        info_df = ak.stock_individual_info_em(symbol=symbol)
        
        # Check if response is valid
        if info_df.empty or "item" not in info_df.columns or "value" not in info_df.columns:
            print(f"⚠️ {symbol} - Invalid or empty data returned")
            industry = "N/A"
            concept = "N/A"
        else:
            # Safely build dictionary
            info_dict = dict(zip(info_df["item"], info_df["value"]))
            industry = info_dict.get("行业", "")
            concept = info_dict.get("概念", "")

        top_150.at[idx, "industry"] = industry
        top_150.at[idx, "concept"] = concept

        print(f"✅ {symbol} - Industry: {industry} | Concept: {concept}")
        time.sleep(0.3)

    except Exception as e:
        print(f"❌ Failed to fetch info for {symbol}: {e}")
        top_150.at[idx, "industry"] = "Error"
        top_150.at[idx, "concept"] = "Error"

if not os.path.exists("breadfree/data/cache/"):
    os.makedirs("breadfree/data/cache/")
    print("\n✅ Cache directory created")

# Save results with English headers
top_150.to_csv("breadfree/data/cache/top_150_with_sectors.csv", index=False, encoding="utf-8-sig")
print("\n✅ Sector information saved")