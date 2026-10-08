# 如何启动 ABB

[English](../Guide.md) | 中文

## 安装前准备

从源码仓库安装并保留该目录。当前 wheel 不包含完整的 Agent 资源和网页构建产物。

| 安装在宿主机 | 用途与检查 |
| --- | --- |
| Git | 下载仓库和 Agent；`git --version`。 |
| Python 3.10+、pip、venv | CLI 与 harness；`python3 --version`。 |
| 已运行且当前用户可访问的 Docker | Docker Agent/正式评测；`docker info` 必须成功。 |
| Node.js 20.x 至少 20.19，或 22.12+，以及 npm | 构建网页；`node --version`、`npm --version`。无界面运行可不安装。 |
| 浏览器 | 打开终端输出的完整本地 URL。 |

网页可以查看 ABB 启动的进程及其运行状态，以及 Agent 输出的内容。

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

如果你尚未接入自己的测试 Agent，默认 SDK 列表应出现 KUMA（CLI 中显示为 `kuma`）和 `local`。
KUMA 是我们为 Benchmark 提供的基线测试 Agent，通过 `kuma` SDK 插件接入；`local` 则是
用于最低限度离线验证的测试 Agent，通过 `local` SDK 插件提供。

离线示例使用本地 echo Agent 和确定性 Judge，无需 Docker、API key 或模型调用。成功时预期显示
`Case execution: 1/1 completed | Judge: pass=1`，表示本地测试流程已跑通。
记录 `OFFLINE_RESULT=` 后的真实路径：程序会给输出文件加时间戳。

如果 demo 提示 `Agent requirement.md is missing`，说明 echo 示例缺少接入文件。
这是示例问题，不是 API key 错误；请使用包含该示例修复的版本。
CLI 帮助与 SDK 列表仍可用于不需要凭据的安装检查。

## 网页构建

ABB 支持使用 `--no-view` 运行 Benchmark 而不启动网页，例如 `agentbench run --no-view`。
仅使用命令行时，无需安装用于构建网页的 Node.js 和 npm。不过，我们强烈建议安装并构建
网页查看器，方便查看 ABB 启动的进程、运行状态及 Agent 输出的内容。

下图为本地网页的 Benchmark 概览，可查看已保存的 Suites、Agents 和 Cases。

![ABB 网页 Benchmark 概览](../figures/abb-web-overview.jpg)

进入具体 Case 的 **Conversation** 页面，可以查看测试输入及 Agent 输出。

![ABB 网页中的 Agent 输入与输出](../figures/abb-web-agent-output.jpg)

```bash
cd web
npm ci
npm run build
cd ..
# 替换为刚才打印的实际文件路径。
agentbench view results/offline-demo-YYYYMMDD-HHMMSS.json
```

首次 clone 后需先完成上述网页构建。打开终端输出的 `View:` 完整地址，
保持命令运行；按 Ctrl+C 关闭查看器。

1. 在侧栏展开 Suite，选择要查看的 Agent 和 Case。运行进度与结果会自动刷新。
2. 在 **Conversation** 查看测试输入和 Agent 输出，在 **Judge** 查看缺陷判定及依据。
3. 在 **Timing** 查看执行时序；展开 **Trace details** 查看 OpenTelemetry 调用轨迹。
4. 返回 **Benchmark Overview**，选择 **KUMA**、**Local** 等 SDK 选项卡查看汇总，
   点击 **Export JSON** 导出当前结果。

前端修改后重新运行 `npm run build`。

## 配置真实评测

### 1. 选择目标 Agent

先从[已加入的 Agents](Agents.zh-CN.md) 中选择你想测试的 Agent，记下它的 `agent_id`。
参考[注册表说明](Registry.zh-CN.md)，在 `resources/registry.toml` 中确认其框架和启用状态。

如果还没有 `.env`，先复制模板；已有配置请保留：

```bash
test -f .env || cp .env.example .env
```

### 2. 配置目标 Agent 的模型

目标 Agent 执行任务需要调用模型，请根据其接入方式填写 `.env`。

**LangGraph Agent**：选择 OpenRouter、DeepSeek 或 GLM，填写所选服务的 API key 和模型名称。
例如使用 OpenRouter：

```dotenv
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
```

也可以使用以下服务，模型名称请填写账号可用且支持目标 Agent 所需功能的模型：

| 模型服务 | API key | 模型名称 |
| --- | --- | --- |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` |
| GLM | `GLM_API_KEY` | `GLM_MODEL` |

默认按 OpenRouter → DeepSeek → GLM 选择第一个已填写 key 的服务。如果填写了多个服务，
可用 `ABB_MODEL_PROVIDER=deepseek` 或 `ABB_MODEL_PROVIDER=glm` 指定选择。
若使用 GLM，请确认 `GLM_API_BASE_URL` 与你的账号及所用 API 服务对应。
需要网页搜索的 Agent 还需填写 `TAVILY_API_KEY`，具体以该 Agent 的配置为准。

**ACP Agent**：这些 Agent 通常有各自推荐或已配置的模型服务。请在 `.env` 中找到对应
Agent 的注释段，填写所需 API key；如有模型名称和 API 地址，也按该 Agent 的要求填写。
例如 MiniMax Code 使用 `MINIMAX_API_KEY`，Qwen Code 使用 `DASHSCOPE_API_KEY`，
使用 GLM 的 Agent 则填写 `GLM_API_KEY`、`GLM_MODEL` 和 `GLM_API_BASE_URL`。
具体要求可查看对应 `resources/agents/<目录>/README.md`，模板见
[`.env.example`](../../.env.example)。

### 3. 使用 KUMA 进行评测

如果使用 KUMA 生成测试用例并提交 Judge，除目标 Agent 的模型配置外，还需填写：

```dotenv
KUMA_API_KEY=
```

ABB 不会自动安装 KUMA SDK。使用 KUMA 时，在运行 ABB 的虚拟环境中直接安装其发行包：

```bash
python -m pip install "kuma-defuzex[otel]>=0.3.3"
```

运行评测时使用 `--sdk kuma`。

使用 `--sdk local` 做冒烟测试时不需要 `KUMA_API_KEY`，仍需配置目标 Agent 使用的模型。

## 先跑一个 Case

运行 Case 前，请确认以下准备工作已完成：

- [ ] 已安装 ABB 并激活对应虚拟环境，`agentbench --help` 能正常运行。
- [ ] Docker 已启动，当前用户执行 `docker info` 成功。
- [ ] 已选定目标 Agent 的 `agent_id`，并在[注册表](Registry.zh-CN.md)中将其设为 `enabled = true`。
- [ ] 已在 `.env` 中填写该 Agent 所需的模型 API key、模型名称及其他配置，如搜索服务的 key。
- [ ] 已选定评测 SDK：使用 KUMA 时已安装 KUMA SDK 并填写 `KUMA_API_KEY`；使用 `--sdk local` 时无需 KUMA key。
- [ ] 如需网页实时查看，已完成 `npm ci` 和 `npm run build`；使用 `--no-view` 可跳过网页构建。

以下以 `react-agent` 为例，测试其他 Agent 时替换为对应的 `agent_id`：

```bash
agentbench observe --list
agentbench evaluate react-agent --cases 1 --no-view
```

一个 Case 可包含多轮输入。`--no-view` 不启动网页，但结果仍保存；可稍后构建网页
再打开。

如需通过网页实时查看运行情况，请先完成网页构建，然后运行：

```bash
agentbench evaluate react-agent --cases 1
```

`run` 执行注册表中全部启用且 ready 的 Agent，Case 数取各自的 `case`。
字段含义及每个 Case 的 `step` 上限见[如何阅读 `registry.toml`](Registry.zh-CN.md)：

```bash
agentbench run
agentbench run --yes --no-view --results-dir results
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

## 接入配置生成失败

`agent add -b` 出现 schema / JSON 错误时，先看[接入指导中的排查说明](How%20To%20Add%20Agent.zh-CN.md#结构化输出生成失败时)。
schema 字段路径和 JSON 行列错误现在会反馈给模型，按现有预算进行纠正。
若步骤仍失败，请保留已完成文件，并检查保存的校验和 provider 诊断记录。
