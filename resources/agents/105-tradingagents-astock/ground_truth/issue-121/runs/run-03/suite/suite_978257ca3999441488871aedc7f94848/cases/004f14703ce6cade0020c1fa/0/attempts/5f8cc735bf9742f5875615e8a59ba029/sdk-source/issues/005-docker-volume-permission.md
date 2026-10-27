# Issue #46: Docker 命名卷权限崩溃 + 部署文档不清

- **GitHub**: https://github.com/simonlin1212/TradingAgents-astock/issues/46
- **报告人**: @tyraanTao（@hotonion / @ljcugb 跟帖）
- **日期**: 2026-05-31
- **状态**: 🟡 Docker 权限已修(v0.2.14)，中文名崩溃待用户贴日志

## 问题

用户反映本地/Docker 部署一堆坑：
1. `tradingagents` / `tradingagents --help` 「找不到文件」
2. 只能猜到要用 docker，容器内启动后报 `[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`
3. @ljcugb 跟帖：输股票名(中文)报错，输代码正常（命令行+web 都是）

## 根因

- **Docker 权限（真 bug）**：`docker-compose.yml` 命名卷 `tradingagents_data` 挂到
  `/home/appuser/.tradingagents`，但镜像里没预建该目录。Docker 对空命名卷会把挂载点建成
  `root:root`，而容器内进程以 `appuser` 运行 → 写缓存被拒。
  - 隔离实测：不预建目录 → 卷根属主 root → `mkdir` 被拒；预建并归属 appuser → 卷根属主
    appuser(1000) → 写入成功。
- **入口命令**：`tradingagents`/`tradingagents-web` 是 `[project.scripts]` 注册的 console
  command，不是文件；用户多半是 PATH 问题或没装好。属文档表述问题。
- **中文名崩溃**：解析链路 `resolve_ticker()` → `_build_name_code_map()` → mootdx
  `client.stocks()`。实测 0.11.7 下 `stocks()` 正常返回 2.7 万条，非版本问题 → 疑似网络/转码
  特例，已请用户贴确切报错 + `pip show mootdx`。

## 修复（v0.2.14）

Dockerfile 在 `USER appuser` 后预建 `/home/appuser/.tradingagents`（cache/logs/memory），
使空命名卷继承 appuser 属主。仅 Dockerfile + 文档改动，Python 零改动。

## 待办

- [ ] 中文名崩溃：等用户日志后定位（resolve_ticker 转码/网络兜底）
- [ ] README 安装/启动段落再打磨（venv、console command、端口映射说明）
