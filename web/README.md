# ABB Trace — Vite + React

最简 Vite + React trace 页面，替代旧静态结果查看器。

```sh
cd web
npm install
npm run dev
```

打开终端显示的本地地址。左侧自动列出 `results/observe/` 下的运行任务，默认加载最新一项。
点击任务即可合并读取它的框架与网络 trace；点击「刷新」更新任务列表和当前任务内容。
每个条目代表一次独立 observe 运行，以运行目录 ID 定位，不按 Agent 合并。
列表只显示通用元数据：`agent_id`、运行 ID、`status` 和记录修改时间；不解析业务输入字段。
因此研究、编程等不同 Agent，以及同一 Agent 的多次运行，都使用相同的展示规则。
没有 trace、文件损坏、读取失败均给出提示。仍可点击「打开 trace 文件」手动多选：

- `results/observe/<run-id>/network.jsonl`
- `results/observe/<run-id>/invocation-*/output/framework.jsonl`

页面按时间排列事件，支持搜索、来源筛选、展开完整 JSON；每次选文件替换当前列表。
也支持 JSON 事件数组。每条记录需包含 `event`，因此 `run.json` 不是 trace 输入文件。
损坏行会提示并跳过；单次文件总大小上限 20 MB，每批显示 100 条。

任务接口由 `server/runs.js` 提供，Vite 开发和 preview 模式均支持，无需另开 Python 服务。
只允许本地同源 GET，限定读取 `results/observe/` 中的 trace，拒绝路径越界，单次最多 20 MB。
手动导入文件不上传；不自动轮询，文件更新后点击刷新。本版不提供图形化 span 树。

原 Python `view` 入口保留，改为提供 `web/dist` 构建产物，并自动加载绑定运行的
原始事件（不再显示旧评测仪表盘）。使用前先 `npm run build`；未构建时页面返回明确提示。
Python 绑定运行模式保持单运行展示；侧边栏用于 Vite dev/preview 模式。

```sh
npm test
npm run build
npm run preview
```

Node.js 需满足 Vite 7 要求（20.19+ 或 22.12+）。
