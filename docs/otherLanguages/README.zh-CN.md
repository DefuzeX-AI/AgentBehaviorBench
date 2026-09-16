# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — 羊驼 Agent 工作流评审" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  中文简体 |
  <a href="README.zh-TW.md">中文繁體</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **运行 ABB 前请先准备：**Python 3.10+、已启动的 Docker Desktop 或 Docker
> Engine，以及用于构建结果查看器的 Node.js 20.19+ 或 22.12+。KUMA 会在构建评测容器时
> 自动从 PyPI 安装。两个内置 Agent 都需要 `KUMA_API_KEY`（或 `DEFUZEX_API_KEY`）、
> `OPENROUTER_API_KEY`、`OPENROUTER_MODEL` 和 `TAVILY_API_KEY`。

AgentBehaviorBench 在隔离运行时中执行已注册的 AI Agent，收集执行证据，并通过
可选 SDK 评测结果。SDK 从 `agentbench/sdk/plugin/` 的适配器目录自动发现：只有一个时
自动选择，有多个时通过 `--sdk NAME` 指定。当前目录包含 KUMA；结果保存在本地，
并可在 ABB 浏览器查看器中检查。

![AgentBehaviorBench 执行架构](../figures/framework.png)

首次运行遇到错误时，请先看下方的[故障排查](#故障排查)。

## 快速开始

在仓库根目录创建虚拟环境，并安装 ABB：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

结果查看器由 `web/` 构建，仓库中不包含构建产物。打开结果前先构建一次；`run`、
`evaluate`、`certify` 结束后会启动它，`agentbench view` 可重新打开已保存的结果：

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
```

创建本地环境文件并填写凭据：

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

`KUMA_API_KEY` 是 KUMA SDK 文档使用的变量名；ABB 也接受别名 `DEFUZEX_API_KEY`，仅在
`KUMA_API_KEY` 为空时使用。`OPENROUTER_MODEL` 必须设置且没有默认值，上面的值只是示例，
请换成你的账户可用的模型。

启动 Docker（`docker info` 应能成功）。检入的注册表启用了两个 Agent，状态都是
`ready`：`react-agent` 和 `company-research-agent`。先评测一个 Case；这会调用按密钥
计费的 KUMA Case 与 Judge 服务：

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

运行所有注册表中 `enabled = true` 且状态为 `ready` 的 Agent：

```bash
agentbench run
```

ABB 会要求确认选中的 Agent，在 `results/` 下保存结果快照并启动本地查看器。无
界面或自动化运行请使用：

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

## 依赖与环境变量

| 项目 | 用途 |
| --- | --- |
| Python 3.10 或更高版本 | ABB 主机 CLI 与 harness。 |
| Docker Desktop / Docker Engine | 内置 Agent 在 Docker 中执行；执行前 Docker 必须已启动。 |
| Node.js 20.19+ 或 22.12+（含 npm） | 构建一次 `web/` 结果查看器；无界面运行（`--no-view`）不需要。 |
| `KUMA_API_KEY` 或 `DEFUZEX_API_KEY` | 使用 KUMA SDK 时所需的 Case 与 Judge 访问凭据。两者都设置时使用 `KUMA_API_KEY`。 |
| `OPENROUTER_API_KEY` | Docker Agent 的模型流量经 ABB interceptor 转发到 OpenRouter。 |
| `OPENROUTER_MODEL` | 必填的模型名。`.env.example` 中的值只是示例，不是运行时默认值；请选择你的账户可用的模型。 |
| `TAVILY_API_KEY` | 两个内置 Agent（ReAct 与 Company Research）的网页搜索凭据。 |

`.env` 被 Git 忽略。Shell 中已导出的变量会覆盖 `.env`；`--env-file PATH` 可选择
其他 dotenv 文件；`--model MODEL` 可只覆盖单次命令的模型。

可选 OpenRouter 设置：

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

运行 `agentbench --help` 或 `agentbench <command> --help` 查看已安装版本的帮助；这是完整的
参数参考。

| 命令 | 用途 |
| --- | --- |
| `agentbench run` | 评测所有启用且 `ready` 的 Agent；这是默认命令。 |
| `agentbench evaluate react-agent --cases 1` | 用指定数量的独立 Case 评测一个 Agent。 |
| `agentbench observe react-agent` | 用原生输入运行一个 Agent 并保存 trace，不创建 Case，也不调用 Judge。 |
| `agentbench certify NEW-AGENT` | 认证 `adapting` Agent；成功后将其提升为 `ready`。 |
| `agentbench view RESULT.json` | 在本地查看器中重新打开结果；路径是运行结束时 `Result saved:` 后打印的文件（带时间戳）。需先构建 `web/`，见快速开始。 |
| `agentbench sdk list` | 列出 SDK 适配器目录，不导入 SDK 实现。 |
| `agentbench clean --dry-run` | 预览 `clean` 会移入 `cache/history-trash/` 的 `results/` 下未被引用的条目；不会删除任何内容。 |

常用 `run` 选项：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

添加 Agent 的完整说明（`agent add`）见[英文 README 的 CLI 一节](../../README.md#cli)（英文），
以及 [agent onboarding guide](../How%20To%20Add%20Agent.md)（英文）。

## 故障排查

以下是首次运行时 `evaluate`、`run` 或 `certify` 输出的常见错误。除模型名一行外，其余
都在任何 KUMA 请求之前停止，不会扣费。

| 输出 | 原因 | 处理 |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker 未启动，或 `DOCKER_HOST` 指向不存在的 daemon。 | 启动 Docker Desktop 或 Docker 服务，直到 `docker info` 成功。 |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | 环境变量和 `.env` 中都没有 KUMA 凭据。 | 在 `.env` 中设置 `KUMA_API_KEY`。 |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | 变量里放的不是 KUMA 密钥，例如误填了 OpenRouter 密钥。 | 使用为 KUMA 签发的 `dfx_` 密钥。 |
| `AuthenticationError: Invalid API key.`，之前有 `GET defuzex.ai/… \| HTTP 401` | KUMA 密钥错误、已吊销，或属于另一个 Backend。 | 更换密钥；如设置了 `KUMA_BASE_URL`，一并检查。 |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | 未设置 `OPENROUTER_MODEL`；ABB 没有默认模型。 | 在 `.env` 中设置 `OPENROUTER_MODEL`，或传入 `--model`。 |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY`（或 `TAVILY_API_KEY`） | 模型上游或 Agent 的 `agent.toml` 需要的凭据缺失。 | 把提示中的变量加入 `.env` 或导出到 shell。 |
| `LLM call 01 \| openrouter \| FAILED`，随后是引用上游消息的 `related network: upstream_error POST …` | 模型上游拒绝了调用，例如模型名不存在，或密钥无权使用该模型。此时 Case 已生成，仍可能被 Judge 并计费。 | 使用上游为你的密钥列出的模型名。 |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | 当前检出中还没有构建查看器。 | 用 Node.js 20.19+ 或 22.12+ 运行提示中的命令。 |

`agentbench clean` 不会删除任何内容：它列出 `results/` 下未被引用的顶层条目，确认后把它们
移入 `cache/history-trash/<时间戳>/`。已保存的 Suite 及其引用的产物保持原位。要撤销，先停止
运行和查看器，再把归档条目移回 `results/`。

## 目录结构

```text
AgentBehaviorBench/
├── resources/registry.toml
├── resources/agents/
├── agentbench/cli/
├── agentbench/harness/
├── agentbench/runtime/
├── agentbench/sdk/plugin/kuma/
├── web/
└── results/
```

- `resources/registry.toml` 声明 Agent、状态和运行时。
- `resources/agents/` 保存每个 Agent 单元及其 ABB 配置。
- `agentbench/cli/` 提供命令行入口。
- `agentbench/harness/` 负责 suite 执行、结果和注册表加载。
- `agentbench/runtime/` 在本地或 Docker 运行 Agent。
- `agentbench/sdk/plugin/` 包含 SDK 适配器、公共接口和目录发现逻辑。
- `web/` 是结果查看器的源码；`npm run build` 生成 CLI 使用的 `web/dist`。

添加 SDK 只需新增包含 `__init__.py` 和 `plugin.py` 的适配器目录，不需要修改
核心名称名单或注册安装包 entry point。参考实现见 `agentbench/sdk/plugin/kuma/`。

## 开发

```bash
python -m pytest
```

仓库约定见 [AGENTS.md](../../AGENTS.md)（英文）。

## 许可证

MIT，见 [LICENSE](../../LICENSE)。
