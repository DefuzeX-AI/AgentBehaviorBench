# ABB Viewer — Vite + React + Redux

本地 Suite 多 Case 总览和独立 Run 的评测、OTel、交互详情。

## 首次安装与普通查看

宿主机需要 Node.js 20.x 至少 20.19，或 22.12+，以及 npm；版本依据
`package-lock.json` 中的 Vite。Python 安装不会安装网页依赖或生成 `dist/`。

```sh
cd web
npm ci
npm run build
cd ..
# 使用评测或离线示例打印的真实路径。
agentbench view results/suites/<suite-id>/events.json
```

普通 `view` 由 Python 提供 `web/dist` 和结果 API，不需要启动 npm 开发服务器。
首次 clone 或前端修改后需要构建；headless 评测使用 `--no-view` 可跳过 Node 和构建。
保持 viewer 命令运行，并打开终端打印的完整 URL。`dist/index.html` 不是独立报告，
直接双击或单独发送它无法获得完整评测页面。

## 前端开发

完成 npm ci 后：

```sh
cd web
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
手动导入文件不上传；本地运行产物每秒同步。OTel 支持执行图和调用树，载荷按需加载。

Python `view` 提供 `web/dist` 构建产物，并自动加载绑定运行的
原始事件。未构建或资源不完整时，CLI 预检查退出并给出构建命令。
绑定 Suite 时默认展示所有 Agent 的全部 Case，可同时展开多个 Case。

## Suite 与恢复

Suite 页面读取 Python 提供的统一快照。Redux 管理快照 revision、筛选、展开位置、
历史 Attempt 选择和恢复命令；执行状态与 Judge 判决分别显示。
详情严格使用该 Attempt 的 `artifact_run_id`，不会通过 Agent 名称猜测运行目录。
断线时保留已有内容，恢复连接后同步；已选历史 Attempt 不自动切换到最新执行。

受控会话提供“继续未完成”和按 Case 恢复。只读历史记录隐藏恢复操作。
命令携带服务提供的控制 token 和幂等 command ID；网络响应不明确时重发原 ID。
导出的当前报告是 JSON 快照，包含全部 Case 和尝试历史，不包含会话控制凭据。
它不打包每个引用的 trace，也不生成独立 HTML；分享完整产物见
[结果与故障排查](../docs/Troubleshooting.md#share-a-report)（英文）。

开发时对照正在运行的 Python Viewer：

```sh
ABB_VIEWER_BACKEND=http://127.0.0.1:<viewer-port> ABB_SUITE_ID=<suite-id> npm run dev
```

这两个值必须同时提供。Vite 将 `/api` 代理给该本地 Viewer，注入准确的 Suite API 路径；
恢复规则只由 Python 实现。未设置时仍使用独立 Run 的只读本地目录 API。
不要用这两个开发环境变量生成要分发的构建，生产页面由 Python 绑定 Suite。

```sh
npm test
npm run build
npm run preview
```

完整安装步骤见 [主 README](../README.md)（英文）和
[中文操作指南](../docs/Guide.zh-CN.md)。
