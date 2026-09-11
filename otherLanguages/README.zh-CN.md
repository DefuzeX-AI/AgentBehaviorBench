# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — 羊驼 Agent 工作流评审" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../README.md">English</a> |
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
> Engine，以及 DefuzeX 可选依赖。内置且可运行的 Company Research Agent 需要
> `KUMA_API_KEY`（或 `DEFUZEX_API_KEY`）、`OPENROUTER_API_KEY`、
> `OPENROUTER_MODEL` 和 `TAVILY_API_KEY`。

AgentBehaviorBench 在隔离运行时中执行已注册的 AI Agent，收集执行证据，并通过
可选 SDK 评测结果。默认 SDK 是内置 KUMA adapter；结果保存在本地，并可在 ABB
浏览器查看器中检查。

![AgentBehaviorBench 执行架构](../figures/framework.png)

## 快速开始

在仓库根目录创建虚拟环境，并安装带 DefuzeX extra 的 ABB：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[defuzex]"
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

启动 Docker 后，运行所有注册表中 `enabled = true` 且状态为 `ready` 的 Agent：

```bash
agentbench run
```

ABB 会要求确认选中的 Agent，在 `results/` 下保存结果快照并启动本地查看器。无
界面或自动化运行请使用：

```bash
agentbench run --no-view --output results/benchmark.json
```

## 依赖与环境变量

| 项目 | 用途 |
| --- | --- |
| Python 3.10 或更高版本 | ABB 主机 CLI 与 harness。 |
| Docker Desktop / Docker Engine | 当前可运行的内置 Agent 在 Docker 中执行；执行前 Docker 必须已启动。 |
| `KUMA_API_KEY` 或 `DEFUZEX_API_KEY` | 默认 KUMA SDK 的 Case 与 Judge 访问凭据。 |
| `OPENROUTER_API_KEY` | Docker Agent 的模型流量经 ABB interceptor 转发到 OpenRouter。 |
| `OPENROUTER_MODEL` | 本次运行使用的模型名称。 |
| `TAVILY_API_KEY` | 内置 Company Research Agent 的网页搜索凭据。 |

`.env` 被 Git 忽略。Shell 中已导出的变量会覆盖 `.env`；`--env-file PATH` 可选择
其他 dotenv 文件；`--model MODEL` 可只覆盖单次命令的模型。

可选 OpenRouter 设置：

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

运行 `agentbench --help` 或 `agentbench <command> --help` 查看已安装版本的帮助。

| 命令 | 用途 |
| --- | --- |
| `agentbench run` | 评测所有启用且 `ready` 的 Agent；这是默认命令。 |
| `agentbench evaluate company-research-agent --cases 1` | 用指定数量的独立 Case 评测一个 Agent。 |
| `agentbench observe company-research-agent` | 用原生输入运行一个 Agent 并保存 trace，不创建 Case，也不调用 Judge。 |
| `agentbench certify react-agent` | 认证 `adapting` Agent；成功后将其提升为 `ready`。 |
| `agentbench view results/benchmark.json` | 在本地查看器中重新打开结果。 |
| `agentbench sdk list` | 列出内置和已安装的评测 SDK。 |
| `agentbench clean --dry-run` | 预览将被移动到可恢复归档的本地结果历史。 |

常用 `run` 选项：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
agentbench run --llm-trace terminal
```

完整参数请见英文 [CLI reference](../docs/CLI.md)，添加 Agent 请见
[agent onboarding guide](../docs/How%20To%20Add%20Agent.md)。

## 目录结构

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

- `resources/registry.toml` 声明 Agent、状态和运行时。
- `resources/agents/` 保存每个 Agent 单元及其 ABB 配置。
- `agentbench/cli/` 提供命令行入口。
- `agentbench/harness/` 负责 suite 执行、结果和注册表加载。
- `agentbench/runtime/` 在本地或 Docker 运行 Agent。
- `agentbench/sdk/` 包含内置 SDK adapter 和插件发现逻辑。

## 开发

```bash
python -m pytest
```

仓库约定见 [AGENTS.md](../AGENTS.md) 和 [docs/AGENTS.md](../docs/AGENTS.md)。

## 许可证

MIT，见 [LICENSE](../LICENSE)。
