# ABB 安装、运行与 Agent 接入

[English](../Guide.md) | 中文

ABB 负责选择 Agent、容器执行、Case 并发、证据和本地结果；KUMA SDK 定义评测
协议，调用 DefuzeX 服务生成 Case 和判分。OpenRouter 是被测 Agent 的模型服务，
Tavily 是部分 Agent 的搜索服务。三类服务的凭据和额度相互独立。

## 安装前准备

从源码仓库安装并保留该目录。当前 wheel 不包含完整的 Agent 资源和网页构建产物。

| 安装在宿主机 | 用途与检查 |
| --- | --- |
| Git | 下载仓库和 Agent；`git --version`。 |
| Python 3.10+、pip、venv | CLI 与 harness；`python3 --version`。 |
| 已运行且当前用户可访问的 Docker | Docker Agent/正式评测；`docker info` 必须成功。 |
| Node.js 20.x 至少 20.19，或 22.12+，以及 npm | 构建网页；`node --version`、`npm --version`。无界面运行可不安装。 |
| 浏览器 | 打开终端输出的完整本地 URL。 |

Node 版本来自仓库锁定的 Vite 依赖。它用于构建/开发网页，普通查看器由 Python
提供 `web/dist`；安装 Python 包不会自动构建网页。

macOS 使用 [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)；
Linux 使用 [Docker Engine](https://docs.docker.com/engine/install/) 并配置当前用户权限；
Windows 建议在 [Docker Desktop + WSL 2](https://docs.docker.com/desktop/features/wsl/)
的 Linux 环境执行以下命令。本轮没有验证原生 PowerShell。Agent 镜像还必须兼容
CPU 架构。首次安装/构建需要访问 pip、npm 和容器镜像及依赖源。

## 零凭据验证与网页构建

```bash
git clone https://github.com/DefuzeX-AI/AgentBehaviorBench.git
cd AgentBehaviorBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
agentbench --help
agentbench sdk list
python -m examples.offline_demo --output results/offline-demo.json
```

SDK 列表应出现 `kuma` 和 `local`。离线示例无需 Docker、API key 或模型调用，预期显示
`Case execution: 1/1 completed | Judge: pass=1`。这验证本地流程，不代表正式服务通过。
记录 `OFFLINE_RESULT=` 后的真实路径：程序会给输出文件加时间戳。

```bash
cd web
npm ci
npm run build
cd ..
# 替换为刚才打印的实际文件路径。
agentbench view results/offline-demo-YYYYMMDD-HHMMSS.json
```

首次 clone 没有 `web/dist`，必须先构建。打开 `View:` 后的完整地址（包括 Suite 路径），
保持命令运行；Ctrl+C 关闭查看器。默认端口 8765 被占用时会换空闲端口。
普通评测不用启动 `npm run dev`；前端修改后需重新构建。

## 配置真实评测

仅在还没有 `.env` 时复制模板，升级时保留已有配置：

```bash
cp .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
ABB_MAX_PARALLEL_CASES=1
```

- `KUMA_API_KEY`：Case/Judge 服务凭据，参考 [DefuzeX 文档](https://defuzex.ai/documentation?view=sdk)
  和 [KUMA 官方仓库](https://github.com/DefuzeX-AI/KUMA-DefuzeX)。`DEFUZEX_API_KEY`
  是 ABB 支持的别名；非空 `KUMA_API_KEY` 优先，只需配置一个。
- `OPENROUTER_API_KEY`：从 [OpenRouter](https://openrouter.ai/settings/keys) 创建。
- `OPENROUTER_MODEL`：必须设置的模型名称，不是密钥。模板里的值只是示例，代码没有
  自动默认值；需确认账号可用、支持 Agent 所需的工具调用和协议。
- `TAVILY_API_KEY`：从 [Tavily](https://app.tavily.com/) 获取，仅使用该工具的 Agent 需要。
- `ABB_MAX_PARALLEL_CASES`：正整数，默认 1；4 表示整个 Suite 最多并行 4 个 Case，
  包括同一 Agent 的不同 Case。它不限制 Agent 内部搜索工具的并发。

Shell 已导出的变量优先于 `.env`，已导出的空值也会影响读取。`--env-file PATH`
选择其他文件，`--model MODEL` 覆盖单次 Agent 模型。`.env` 不会整份挂入容器，
Agent 只获得声明的配置与运行时提供的凭据。当前 ReAct 的模型经拦截器转发，
宿主机无需再提供真实 `ANTHROPIC_API_KEY`。

需要在宿主机做 KUMA 检查或 `agent add -b` 时，在当前 venv 安装：

```bash
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
python -c "from importlib.metadata import version; import kuma; print(version('kuma-defuzex')); print(kuma.__file__)"
```

发行包叫 `kuma-defuzex`，导入名叫 `kuma`。容器也会独立安装该 requirements；
容器安装成功不等于 IDE/宿主机已安装。不要使用旧的 `.[defuzex]` extra。

## 先跑一个 Case

```bash
agentbench observe --list
agentbench evaluate react-agent --cases 1 --no-view
```

一个 Case 可包含多轮输入。`--no-view` 不启动网页，但结果仍保存；可稍后构建网页
再打开。`run` 执行注册表中全部启用且 ready 的 Agent，Case 数取各自的 `case`：

```bash
agentbench run
agentbench run --yes --no-view --output results/benchmark.json
```

`ready` 只代表接入已认证，不代表每个 Case 都能通过 Judge。注册表是当前 Agent 名称、
数量、启用状态和 Case 数的依据。不要按旧 README 中的 Agent 列表推断。

## 不花 KUMA credit 的冒烟测试

`--sdk local` 与 `kuma` 使用同一套容器、模型拦截和宿主机 trace 校验，只是 Case 换成
固定的通用问题、Judge 在本地运行，不经过 KUMA Backend。它不需要 `KUMA_API_KEY`，
也不消耗 KUMA credit；Agent 自己的模型调用照常计费。适合在付费评测前确认 Agent 能从
出题一路跑到出判决。它的判决不是 KUMA 的行为评估。

```bash
agentbench evaluate react-agent --sdk local --cases 1 --no-view
```

- 每个 Case 最多问三个关于 Agent 自身的通用问题，注册表的 `step` 上限仍然生效。
- 某一步失败判 `issue`，某一步没有 SDK trace 证据判 `insufficient_evidence`；否则用
  一次宽松的模型调用检查回答是否连贯。这次调用由宿主机发出，不经过容器，所以 key
  不会进入 Agent 容器，这次调用也不会被记成 Agent 的证据。
- Judge 默认使用 Agent 的模型目标（`OPENROUTER_BASE_URL`、`OPENROUTER_MODEL`、
  `OPENROUTER_API_KEY`）。`ABB_LOCAL_JUDGE_BASE_URL`、`ABB_LOCAL_JUDGE_MODEL`、
  `ABB_LOCAL_JUDGE_API_KEY` 可以改用其他 OpenAI 兼容的 chat completions 端点；
  Agent 的模型目标是 Anthropic messages 协议时必须设置。
- 不写 `--sdk` 的命令仍然使用 `kuma`；`local` 只能按名字选择。
- 运行目录里除常规产物外还有 `local-judge.json`，记录 Judge 模型、判决和原始回复。

## 添加 Agent

请按 [Agent 接入指南](How%20To%20Add%20Agent.zh-CN.md) 操作：先配置环境，
再运行添加命令，最后了解每个文件的用途。该指南提供与 README 相同的六种语言。

## 结果与故障处理

| 现象 | 判断与处理 |
| --- | --- |
| `Trace UI not built` | 先检查 Node 版本，再在 web/ 执行 npm ci 和 npm run build。 |
| Docker 不可用 | 当前用户执行 docker info，检查服务、context 和权限。 |
| SDK 导入错误 | 安装插件 requirements；IDE 选择同一个 venv。 |
| key/model 错误 | 分清 KUMA、模型、搜索服务；检查环境优先级、模型 slug 和额度。 |
| `-b` schema 错误 | 检查生成模型是否支持严格结构化输出，以及失败阶段记录。 |
| `FAILED` 但有 Judge | 查看执行状态和 Judge 状态，不能直接判断容器崩溃。 |
| `issue` | 已发现行为问题，核对具体步骤和实际 trace。 |
| `insufficient_evidence` | 证据不足，不能直接当作已证实的 Agent 缺陷。 |
| OTel `partial` | 看具体原因；属性过滤、span 丢失、导出失败并不相同。 |

Suite 在 `results/suites/<suite-id>/` 保存计划、Case 和 events.json；每次执行的
详细产物在 `results/observe/<run-id>/`。Judge 通常位于 evaluation/judge/report.json。
始终使用终端打印的真实路径和 Case 的 artifact ID。

`resume SUITE` 继续符合恢复条件的未完成任务；`retry SUITE --agent ID --case N`
恢复一个未完成 Case；`reuse SUITE` 用保存的 Case 创建新 Suite。已接受但响应不明、
非安全重放或清理未确认的请求仍可能阻塞，不承诺任何失败都可自动重试。
改 Profile 不会改变旧 Case；验证新 Profile 要重新生成。

网页的 Export current report 导出 **JSON 快照**，不打包全部 trace，也不是独立 HTML。
完整结果需保留 Suite 和引用的执行目录；跨机器路径可能需要调整。
`web/dist/index.html` 依赖其他资源与本地 API，单独发送它不够。

`agentbench clean --dry-run` 预览历史归档。正式 clean 保留被 Suite 引用的产物，
把其他历史移到 `cache/history-trash/`，不删除 Agent、key、注册表或 Docker 镜像。
先停止运行与查看器，再确认清理。

更详细的限制见 [故障排查（英文）](../Troubleshooting.md) 和
[文档 issue 核对记录（英文）](../Documentation-Issue-Audit.md)。
