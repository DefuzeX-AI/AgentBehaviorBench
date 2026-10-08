import akshare as ak
import pandas as pd
import os
from datetime import datetime, timedelta

# 定义要轮动的ETF列表（代码 + 名称）
etf_pool = {
    "510300": "沪深300ETF",      # 大盘基准
    "510500": "中证500ETF",      # 中小盘
    "159915": "创业板ETF",       # 成长风格
    "512880": "证券ETF",         # 强周期
    "510880": "红利ETF",         # 防御价值
    "513100": "纳指ETF",         # 海外资产
    "512660": "军工ETF",         # 独立行情
    "511260": "国债ETF",         # 避险资产
    "159949": "黄金ETF",         # 大宗商品
}

# 设置时间范围（例如过去5年）
end_date = datetime.today().strftime("%Y%m%d")
start_date = (datetime.today() - timedelta(days=10*365)).strftime("%Y%m%d")

# 创建存储完整数据的目录
data_dir = "breadfree/data/cache/etf_data"
os.makedirs(data_dir, exist_ok=True)

# 存储所有ETF价格数据
price_dict = {}

for code, name in etf_pool.items():
    try:
        # 获取ETF日线数据（前复权）
        df = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        if df.empty:
            print(f"⚠️ {code} ({name}) 数据为空，跳过")
            continue

        # 保存完整量化数据到独立CSV
        full_data_path = os.path.join(data_dir, f"{name}.csv")
        df.to_csv(full_data_path, index=False, encoding='utf-8-sig')

        # 保留日期和收盘价，并设置索引（用于生成汇总表）
        df['日期'] = pd.to_datetime(df['日期'])
        df.set_index('日期', inplace=True)
        price_dict[code] = df['收盘']
        print(f"✅ 已下载并保存完整数据 {code} ({name})，共 {len(df)} 条记录")
    except Exception as e:
        print(f"❌ 下载 {code} ({name}) 失败: {e}")