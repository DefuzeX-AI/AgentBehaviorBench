# ABB 安装、运行与 Agent 接入

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

SDK 列表应出现 `kuma`。离线示例无需 Docker、API key 或模型调用，预期显示
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

## 添加 Agent

### 1. 先把环境配好

完成上面的 ABB/宿主机 KUMA 安装和 `.env` 配置：KUMA key 用于策略目录及评测，
OpenRouter key 和模型用于生成配置与执行 Agent。生成模型必须支持严格结构化输出；
`docker info` 必须成功。需要网页时先构建 web/，否则加 `--no-view`。
再按目标仓库的说明准备它自己的工具 key、数据和外部服务。

生成模型按 `--build-model`、build settings 的 `model`、`OPENROUTER_BUILD_MODEL`、
`OPENROUTER_MODEL` 顺序选取；`--model` 单独控制认证时的 Agent 模型。

### 2. 运行添加命令

用户或协助接入的 coding agent 都可以从 ABB 根目录执行，替换目标仓库 URL：

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`：生成并验证接入文件，登记为 adapting，不是立即构建 Docker 镜像。
- `-c`：进入实际容器认证，通过执行验收后变为 ready。
- 不需要网页时追加 `--no-view`。

程序会下载源码、规划接入、逐文件生成和验证，然后询问是否进行认证。
生成与认证可能产生费用。目前自动配置支持 LangGraph，不代表任意 Agent 仓库都可直接运行。

想先检查生成的文件，去掉 `-c`：

```bash
agentbench agent add https://github.com/owner/repository -b
```

两个参数都不加时，只下载源码、输出发现的配置路径，不会生成接入文件或注册可运行 Agent。

### 3. 了解每个文件做什么

接入文件位于 `resources/agents/NN-name/`，由命令生成，不要求用户在运行命令前手写齐全。

| 文件 | 作用 |
| --- | --- |
| `agent/` | 下载的原始 Agent 源码，保留真实推理和工具行为。 |
| `agent.toml` | 告诉 ABB 如何构建、启动、调用 Agent，以及输入输出映射、环境变量、模型和工具路由。 |
| `bindings/*.py` | 连接 ABB 与原生 Agent，处理格式转换和生命周期；不能替换成假的简化 Agent。 |
| `Dockerfile` | 安装容器内依赖，复制源码和接入文件；宿主机安装不等于容器已安装。 |
| `.dockerignore` | 排除 key、宿主机 venv、缓存和结果，保留构建所需源码；由 ABB 模板生成。 |
| `requirement.md` | 向 SDK 描述实际能力、行为要求和限制，指导评测；它不会给 Agent 增加工具。 |
| `evaluation/` | 可选的 schema/fixture；没有引用时不用创建，也不要求 input-contract.json。 |
| `resources/registry.toml` | 位于单元之外，登记路径、启用状态、adapting/ready 和 Case 数量。 |

Profile 要写已部署的能力，而不是“理论上可以扩展”：只有搜索工具就明确没有代码执行、
文件持久化或服务控制能力。策略组从当前 SDK 目录选择，不照抄历史 ID。

`source-manifest.json` 是**下载器自动生成的内部来源记录**，用于识别仓库和 revision、
复用下载；不是 KUMA 要求用户准备的配置文件。
`cache/onboarding/<unit-name>-<path-digest>/` 下的计划、steps 和 build-state.json
也是自动记录，不属于 Agent 源码。

只运行 `-b` 后，可准备与 binding 匹配的 native-input.json，再逐步验证：

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

`observe` 不调用 Case/Judge，但模型和工具仍可能收费。`evaluate --cases 1` 不修改
注册表数量，`certify` 使用注册表中的 Case 数。Judge issue 可以与认证成功并存。
已 ready 时 `certify` 直接返回，修改后的重新验证使用 `evaluate`。

生成中断时看 `build-result.json` 和失败步骤，修正后重跑原 `-b` 命令；它会复用有效文件，
人工文件冲突会停止。规划需要补充信息时可加 `--answers answers.txt`。
详细说明见 [Agent 接入指南（英文）](How%20To%20Add%20Agent.md)。

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

更详细的限制见 [故障排查（英文）](Troubleshooting.md) 和
[文档 issue 核对记录（英文）](Documentation-Issue-Audit.md)。
