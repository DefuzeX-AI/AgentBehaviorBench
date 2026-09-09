# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench (ABB)"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
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
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## 最新动态

- AgentBehaviorBench (ABB) 现在通过 DefuzeX SDK 的 `get_input()` / `submit()` 握手流程运行已注册的 LangGraph Agent。

## 概览

AgentBehaviorBench (ABB) 是一个用于评估 AI Agent 的基准测试工具，面向需要调用目标 Agent、收集其输出和执行轨迹，并判断其是否正确完成指定工作流的端到端任务。

给定一个已注册的 Agent 和一个 benchmark Case，AgentBehaviorBench (ABB) 会通过受信任的宿主 harness 运行该 Agent。该 harness 可以启动特定框架或容器化的 Agent，通过凭据安全的 Model Interceptor 路由模型流量，将每个 SDK input 和 Agent response 记录为原子更新的 JSON 事件，并把完成的运行提交给 DefuzeX Judge。

AgentBehaviorBench (ABB) 旨在让 Agent 评估具备可复现性。Agent 在 registry 中声明，通过 LangGraph 等框架 adapter 接入，从 `adapting` 认证到 `ready`，并且只有在认证成功后才会进入默认 benchmark 运行。

当前执行流程如下：

```text
registry.toml
-> SuiteRunner
-> BenchmarkRunner
-> DefuzeX SDK Run
-> Agent Adapter / Runtime
-> Judge Report
```

仓库包含：

- `agentbench/cli`：终端入口和进度输出。
- `agentbench/harness`：SDK 握手、suite 执行、结果和 registry。
- `agentbench/adapter`：框架无关的 adapter contract 和 LangGraph 支持。
- `agentbench/runtime`：本地和 Docker runtime 集成。
- `resources/agents`：可复现的 benchmark Agent fixture。
- `services/model-interceptor`：Docker 运行中用于模型 provider 访问的透明拦截服务。

![AgentBehaviorBench (ABB) framework](../figures/framework.png)

## 安装

AgentBehaviorBench (ABB) 需要 Python 3.10 或更高版本，以及 DefuzeX Python SDK。SDK 提供 AgentBehaviorBench (ABB) 使用的 benchmark protocol：解析 benchmark requirements、创建 DefuzeX Cases、驱动每个 SDK input、记录 evidence，并提交完成的 runs 进行 judging。

在包含本仓库的父级 workspace 中创建并激活虚拟环境：

```powershell
cd <workspace-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

以 editable mode 安装 AgentBehaviorBench (ABB)：

```powershell
python -m pip install -e .\defuzeX_AgentBench
```

### 内部 SDK 构建

本仓库目前依赖内部 DefuzeX SDK 的 `dev` 分支。在 SDK 支持常规 package 安装之前，如果本地尚未 clone `Defuze-SDK`，请从 SDK `dev` 分支（`https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev`）clone 到 `defuzeX_AgentBench` 旁边，然后安装到同一个 `.venv`：

```powershell
cd <workspace-root>
git clone --branch dev --single-branch https://github.com/DefuzeX-AI/Defuze-SDK
python -m pip install -e .\Defuze-SDK
python -m pip install -e .\defuzeX_AgentBench
```

典型的源码 checkout 会把 `Defuze-SDK` 和 `defuzeX_AgentBench` 作为同一个父级 workspace 下的兄弟目录，并将二者都以 editable mode 安装。

> [!NOTE]
> PAT 表示 Personal Access Token。如果内部 DefuzeX SDK 仓库是私有的，GitHub 可能会要求在通过 HTTPS clone 时提供 PAT。请把 PAT 当作密码处理：不要把它写入源文件、README 示例、notebook 或已提交的 `.env` 文件。

## 使用

安装 AgentBehaviorBench (ABB) 后，从 benchmark workspace 使用 launcher script 启动：

```powershell
cd <workspace-root>
.\.venv\Scripts\Activate.ps1
python .\run_agentbench.py
```

也可以直接从 AgentBehaviorBench (ABB) 仓库运行 package：

```powershell
cd <workspace-root>\defuzeX_AgentBench
python -m agentbench
```

如需保存一次运行并在本地 result viewer 中查看实时 benchmark events，请传入 output path：

```powershell
python -m agentbench --output results\result.json
```

不传 `--output` 时，AgentBehaviorBench (ABB) 会在终端中运行，并且不会创建 JSON result artifact。传入 `--output` 时，AgentBehaviorBench (ABB) 会写入一个原子更新的 JSON result file，并启动本地 viewer，便于你在 benchmark 运行期间刷新和检查 events。

使用官方 Case 或 Judge providers 时，请设置 DefuzeX API key：

```powershell
$env:DEFUZEX_API_KEY = "dfx_<public-id>.<secret>"
```

运行测试套件：

```powershell
python -m pytest
```

更多面向 Agent 的说明，请从 [AGENTS.md](../AGENTS.md) 开始。更完整的文档指南位于 [docs/AGENTS.md](../docs/AGENTS.md)。

## 如何添加待测试 Agent

如果你想把自己的 Agent 添加到 benchmark，请让 agent 阅读 [docs/How To Add Agent.md](../docs/How%20To%20Add%20Agent.md)，并按照其中记录的 onboarding flow 操作。

AgentBehaviorBench (ABB) 提供了把外部 Agent project 转换为可重复 benchmark target 所需的组件：基于 registry 的 discovery、framework adapters、Docker runtime support、通过 Model Interceptor 路由模型凭据、只追加 result artifacts、本地 result viewing，以及从 `adapting` 到 `ready` 的 certification。这让你可以用同一组 DefuzeX Cases 一致地比较不同 Agent，同时保持 runtime behavior、outputs 和 judgment evidence 可检查。

## 引用和许可证

MIT License。见 [LICENSE](../LICENSE)。

如果你觉得我们的工作有帮助，请按如下方式引用：
