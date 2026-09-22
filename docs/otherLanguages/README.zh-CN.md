# AgentBehaviorBench（ABB）

<p align="center">
  <img
    alt="AgentBehaviorBench — 对 Agent 工作流进行行为评测"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  中文 |
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 或更高版本" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## ABB 是什么？

AgentBehaviorBench 是一个面向 AI Agent 的行为测试系统。它评估 Agent 在具体任务中的
真实行为，包括 Agent 收到了什么指令、调用了哪些模型和工具、对外部状态做出了哪些修改，
以及采集到的证据是否能够支持 Agent 的最终回答。

ABB 不只比较 Agent 最后输出的文本。一个 Case 可以测试安全边界、指令处理、工具使用、
状态变化，以及 Agent 是否如实报告了自己的操作。每次评测都会保存 Case、Agent 输出、
执行证据和 Judge 结果，方便后续检查和复现。

## 架构概览

ABB 可以注册许多由不同框架实现的 Agent，并让它们通过同一套行为评测流程运行。评测 SDK
根据 Agent 声明的能力生成 Cases，ABB 在隔离运行环境中执行每个 Case，采集模型调用、
工具调用、文件变化和 Agent 输出，然后由评测 SDK 根据这些证据进行 Judge 评审。

![AgentBehaviorBench 架构](../figures/abb-architecture-v2.png)

Agent Registry 记录当前测试的是哪个 Agent 源码版本，以及 ABB 应当如何启动它。ABB Harness
负责调度 Cases、启动隔离容器、执行 Agent Run、路由已声明的模型和工具流量，以及采集调用链
和文件系统证据。Agent 的执行状态与 Judge 判定是两个不同的概念：容器和 Agent 可能成功执行，
但 Judge 仍然可能发现行为问题。

## 当前已导入的 Agents

下面列出了当前已经注册到 ABB 的 Agent 源码。

ABB 目前支持原生接入 LangGraph Agent，也支持通过 Agent Client Protocol（ACP）接入兼容该
协议的 Agent。

每个 GitHub revision 链接都指向对应 `agent.toml` 中固定的确切 commit。Folder Mover Agent
是从本地目录导入的，因此 ABB 保存的是源码内容摘要，而不是 Git commit。

| Agent | GitHub 源码 | 固定版本 |
| --- | --- | --- |
| `folder-mover-agent` | 本地源码目录 | `sha256:2826f61…` |
| `company-research-agent` | [guy-hartstein/company-research-agent](https://github.com/guy-hartstein/company-research-agent) | [`c714203`](https://github.com/guy-hartstein/company-research-agent/commit/c7142035a1cd413e34ad0595dbe9b5ca8b0308e8) |
| `react-agent` | [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) | [`9bbd82d`](https://github.com/langchain-ai/react-agent/commit/9bbd82d84905acc37f527b1f372dae841016f3b4) |
| `ai-hedge-fund-crypto` | [51bitquant/ai-hedge-fund-crypto](https://github.com/51bitquant/ai-hedge-fund-crypto) | [`c6750e0`](https://github.com/51bitquant/ai-hedge-fund-crypto/commit/c6750e0041cb2e528856864783585427c45cc34d) |
| `labscript-ai` | [KRATSZ/LabScript-AI](https://github.com/KRATSZ/LabScript-AI) | [`abff772`](https://github.com/KRATSZ/LabScript-AI/commit/abff77285eacc98f245a27059d7d2c34969dcc2c) |
| `multi-agent-cad` | [Pan-Chera/Multi-Agent-CAD](https://github.com/Pan-Chera/Multi-Agent-CAD) | [`f31a2f6`](https://github.com/Pan-Chera/Multi-Agent-CAD/commit/f31a2f65aa1b1e16fa6c45f1d642142fb696db28) |
| `autoresearch-agents` | [hwchase17/autoresearch-agents](https://github.com/hwchase17/autoresearch-agents) | [`552fd6a`](https://github.com/hwchase17/autoresearch-agents/commit/552fd6a1bd607f6645cd4baba0a98858d62e8815) |
| `langchain-streamlit-template` | [hwchase17/langchain-streamlit-template](https://github.com/hwchase17/langchain-streamlit-template) | [`3c676a6`](https://github.com/hwchase17/langchain-streamlit-template/commit/3c676a670d1f69bcc4c76b692126db1922101d5f) |
| `curiosity` | [jank/curiosity](https://github.com/jank/curiosity) | [`41c9195`](https://github.com/jank/curiosity/commit/41c91954788f04b15332d2b86e265c5433fa4813) |
| `readwren` | [muratcankoylan/readwren](https://github.com/muratcankoylan/readwren) | [`3d0bfe4`](https://github.com/muratcankoylan/readwren/commit/3d0bfe481a340f247c749c082b7a65c877c12de1) |
| `tablegpt-agent` | [tablegpt/tablegpt-agent](https://github.com/tablegpt/tablegpt-agent) | [`26bc576`](https://github.com/tablegpt/tablegpt-agent/commit/26bc576bb21fc1c296d829e863c97290e92bfd8e) |
| `minimax-code` | [MiniMax-AI/minimax-code](https://github.com/MiniMax-AI/minimax-code) | [`a5639bc`](https://github.com/MiniMax-AI/minimax-code/commit/a5639bcc6146754e01f1ae18bb88545f18299fd6) |
| `claude-agent-acp` | [agentclientprotocol/claude-agent-acp](https://github.com/agentclientprotocol/claude-agent-acp) | [`d421f56`](https://github.com/agentclientprotocol/claude-agent-acp/commit/d421f56a6c43cde16d9a7531d08a750a5ef2f04a) |
| `qwen-code` | [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) | [`1026c4a`](https://github.com/QwenLM/qwen-code/commit/1026c4a50f4a32f77da98bdacfba2e5faa8cc70a) |
| `opencode` | [anomalyco/opencode](https://github.com/anomalyco/opencode) | [`014614d`](https://github.com/anomalyco/opencode/commit/014614d35b397775e5d397a490fc72368c894ec2) |
| `kilo-code` | [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode) | [`01ef456`](https://github.com/Kilo-Org/kilocode/commit/01ef456fe7f41aa1f7b8a4e6b545dd1e0fbeeceb) |
| `goose` | [aaif-goose/goose](https://github.com/aaif-goose/goose) | [`1a4249a`](https://github.com/aaif-goose/goose/commit/1a4249ac9f23c6e6e2526d4b54dbbf3bb09ba204) |
| `cline` | [cline/cline](https://github.com/cline/cline) | [`d718dd1`](https://github.com/cline/cline/commit/d718dd16f850c4c915a8214441a831e00cb28c75) |
| `kimi-cli` | [MoonshotAI/kimi-cli](https://github.com/MoonshotAI/kimi-cli) | [`86f1364`](https://github.com/MoonshotAI/kimi-cli/commit/86f136422a0aae6b217ea49e7ea1d2e8a1defcd2) |
| `pi-coding-agent` | [earendil-works/pi](https://github.com/earendil-works/pi) | [`13cbf77`](https://github.com/earendil-works/pi/commit/13cbf77df2396303013a41646bcfa77b4271ae56) |
| `copilot-cli` | [github/copilot-cli](https://github.com/github/copilot-cli) | [`ab6139c`](https://github.com/github/copilot-cli/commit/ab6139c694ba09ab4e8ac76b6046daa6b5d89616) |
| `openclaw` | [openclaw/openclaw](https://github.com/openclaw/openclaw) | [`ec9c1a1`](https://github.com/openclaw/openclaw/commit/ec9c1a13db8938e5a3eaa51fca2e981cde2395a9) |
| `hermes-agent` | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | [`345cd2b`](https://github.com/NousResearch/hermes-agent/commit/345cd2b057a452236de401d3534b8502a7465e8d) |
| `openhands` | [OpenHands/OpenHands-CLI](https://github.com/OpenHands/OpenHands-CLI) | [`2963442`](https://github.com/OpenHands/OpenHands-CLI/commit/2963442dacc7cea44e39b7c4e73724295c853465) |
| `deepagents-code` | [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | [`a764619`](https://github.com/langchain-ai/deepagents/commit/a764619aa8c850bc75e2e916cf53a587637d8c81) |

`resources/registry.toml` 是 Agent 启用状态、就绪状态、Case 数量和 step 上限的权威数据来源。

## 评测 SDK 与 Judge

ABB 的正式评测当前使用 [KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX)，
固定版本为 `kuma-defuzex[otel]==0.3.1`。KUMA 生成行为测试 Cases，接收 ABB 采集的执行
证据，并将其提交给 DefuzeX Judge。Judge verdict 和评审信息会与 Suite artifacts 一起保存。

ABB 还包含一个 `local` SDK 插件，用于确定性的离线开发、演示和测试。它不是正式 Benchmark
结果所使用的 Judge。

## ABB CLI 指令

```text
usage: agentbench [-h]
                  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
                  ...

运行、认证并检查已经注册的 Benchmark Agents。

位置参数：
  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
    run                 运行所有已启用且状态为 ready 的 Agents。
    agent               导入和检查用于接入 ABB 的 Agent 源码。
    view                在本地 Viewer 中打开已保存的评测结果。
    certify             运行一个 adapting Agent，并在执行成功后将其升级为 ready。
    observe             运行一个已启用的 Agent 并保存执行 traces。
    evaluate            使用相互独立的 SDK Cases 评测一个 Agent。
    clean               归档未被引用的本地历史结果。
    sdk                 列出并检查评测 SDK 插件。
    resume              继续运行一个已保存 Suite 中尚未完成的任务。
    retry               使用原始输入重新运行一个尚未完成的 Case。
    reuse               使用已保存的 Cases 创建并运行一个关联的新 Suite。

选项：
  -h, --help            显示帮助信息并退出
```

运行 `agentbench COMMAND --help` 可以查看某个子命令的完整参数。

## 更多文档

- [如何安装、配置和启动 ABB](Guide.zh-CN.md)
- [如何将一个 Agent 添加到 ABB 进行测试](How%20To%20Add%20Agent.zh-CN.md)
- [完整安装、运行、恢复和开发参考（英文）](../README-previous.md)
- [结果说明和故障排查（英文）](../Troubleshooting.md)

## 许可证

MIT，详见 [LICENSE](../../LICENSE)。
