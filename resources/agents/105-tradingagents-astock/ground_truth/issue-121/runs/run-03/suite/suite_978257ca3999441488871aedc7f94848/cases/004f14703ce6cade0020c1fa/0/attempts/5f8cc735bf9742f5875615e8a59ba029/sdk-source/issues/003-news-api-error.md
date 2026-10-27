# Issue #3: 新闻接口异常

- **GitHub**: https://github.com/simonlin1212/TradingAgents-astock/issues/3
- **报告人**: @fengyunzyl
- **日期**: 2026-05-14
- **状态**: ⏳ 等待反馈

## 问题

用户报告新闻接口异常，具体报错未贴出。

## 回复

实测 akshare 1.18.60 的 `ak.stock_news_em` 正常可用。`invalid escape sequence: \u` 错误大概率是 akshare 版本过旧导致（pandas 3.0 + pyarrow 的正则兼容问题，同 a-stock-data#2）。

建议升级 akshare 或使用东方财富原始接口。

## 关联

与 a-stock-data Issue #2 相同根因（akshare 上游 bug：`regex=True` 应为 `regex=False`）。
