# Issue #2: ticker contains characters not allowed in a filesystem path

- **GitHub**: https://github.com/simonlin1212/TradingAgents-astock/issues/2
- **报告人**: @badandboy
- **日期**: 2026-05-14
- **状态**: ✅ 已修复
- **复现人数**: 5+（@badandboy, @xboffice, @xyangwang, @Haevendoor, @jshaofa-ui）

## 问题

`safe_ticker_component` 只允许 ASCII 字符（`[A-Za-z0-9._\-\^]`），当 LLM 在 tool call 中返回中文股票名（如"福晶科技"）而不是 6 位代码时，直接报 ValueError。

deepseek-v4-flash 等模型尤其容易触发，同一次分析中 news_analyst 正常但 policy_analyst 报错，说明模型不一定每次都遵守工具描述中的格式要求。

## 修复（两层）

### 第一层：UI + 工具描述（提交 453c6b5）
- sidebar.py：用户输入中文名时先 `resolve_ticker()` 转成 6 位代码
- 所有 tool annotation 强化为 "Must be numeric, NOT company name"

### 第二层：兜底防线（提交 85e7eb5）
- `safe_ticker_component` 检测到中文字符时自动调 `resolve_ticker()` 转码
- 通过 mootdx 全市场股票映射表（缓存）实现 中文名 → 6 位代码

## 验证

```
福晶科技 → 002222 ✅
宁德时代 → 300750 ✅
../etc/passwd → ValueError ✅（路径穿越仍被拦截）
```
