# Issue #1: No module named 'mootdx'

- **GitHub**: https://github.com/simonlin1212/TradingAgents-astock/issues/1
- **报告人**: @badandboy
- **日期**: 2026-05-14
- **状态**: ✅ 已修复

## 问题

mootdx 和 akshare 未写入 pyproject.toml 依赖列表，用户 pip install 后运行报 `No module named 'mootdx'`。

## 修复

提交 515d297：将 mootdx 和 akshare 加入 pyproject.toml dependencies。

## 遗留问题

mootdx 锁死 httpx==0.25.2，与 langchain-google-genai 要求的 httpx>=0.28.1 冲突。

**临时方案**（不用 Google 模型时）：
```bash
pip install mootdx --no-deps
pip install tdxpy prettytable tenacity
```

**根因**：mootdx 上游依赖过旧，需要等上游更新或考虑 fork/替换。
