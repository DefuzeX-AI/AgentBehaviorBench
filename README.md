# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench — llama agents reviewing workflows"
    src="docs/figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  English |
  <a href="docs/otherLanguages/README.fr.md">Français</a> |
  <a href="docs/otherLanguages/README.ja.md">Japanese</a> |
  <a href="docs/otherLanguages/README.zh-CN.md">中文</a> |
  <a href="docs/otherLanguages/README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## What is ABB?

AgentBehaviorBench is a behavioral testing system for AI Agents. It evaluates
what an Agent does in a concrete task: the instructions it receives, the model
and tool calls it makes, the changes it produces, and whether the collected
evidence supports its final answer.

ABB tests behavior rather than only comparing final text. A Case may probe
safety boundaries, instruction handling, tool use, state changes, or whether an
Agent reports its actions truthfully. Each run preserves the Case, Agent output,
captured evidence, and Judge result for review.

## Overview

ABB can register many Agents implemented with different frameworks and run them
through one evaluation pipeline. An evaluation SDK generates Cases from each
Agent's declared capabilities, ABB executes every Case in an isolated runtime,
and the SDK judges the observed behavior using the captured evidence.

![AgentBehaviorBench architecture](docs/figures/abb-architecture-v2.png)

The Agent registry records which source revision is under test and how ABB can
launch it. The harness schedules Cases, starts containers, routes declared model
and tool traffic, and captures traces and filesystem evidence. Execution status
and Judge verdict are reported separately: a container may run successfully
while the Judge still finds a behavioral issue.

## Imported Agents

The following Agent sources are currently registered.

ABB currently supports native LangGraph Agents and Agents exposed through the
Agent Client Protocol (ACP).

Each GitHub revision link points to the exact commit selected by its `agent.toml`.
The Folder Mover Agent was imported from a local checkout, so ABB records a content
digest instead of a Git commit.

| Agent | GitHub source | Selected revision |
| --- | --- | --- |
| `folder-mover-agent` | Local checkout | `sha256:2826f61…` |
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

`resources/registry.toml` is the authoritative source for enabled state, readiness,
Case counts, and step limits.

## Evaluation SDK and Judge

Official evaluations currently use the
[KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX), pinned as
`kuma-defuzex[otel]==0.3.1`. KUMA generates behavioral Cases, accepts the evidence
captured by ABB, and submits it to the DefuzeX Judge. The resulting verdict and
supporting assessment are stored with the Suite artifacts.

ABB also includes a `local` SDK plugin for deterministic offline development and
tests. It is not the official Judge used for benchmark results.

## ABB CLI help

```text
usage: agentbench [-h]
                  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
                  ...

Run, certify, and inspect registered benchmark Agents.

positional arguments:
  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
    run                 Run all enabled Agents whose status is ready.
    agent               Import and inspect Agent source for onboarding.
    view                Open a saved benchmark result in the local viewer.
    certify             Run one adapting Agent and promote it to ready after
                        execution succeeds.
    observe             Run one enabled Agent and save traces
    evaluate            Evaluate one Agent on independent SDK Cases
    clean               Archive unreferenced local result history.
    sdk                 List and inspect evaluation SDK plugins.
    resume              Continue unfinished work in a saved Suite.
    retry               Retry one unfinished Case using its original inputs.
    reuse               Run all saved Cases in a linked new Suite.

options:
  -h, --help            show this help message and exit
```

Run `agentbench COMMAND --help` for command-specific options.

## More documentation

- [How to install, configure, and run ABB](docs/Guide.md)
- [How to add an Agent to ABB for testing](docs/How%20To%20Add%20Agent.md)
- [Detailed setup, operation, recovery, and development reference](docs/README-previous.md)
- [Results and troubleshooting](docs/Troubleshooting.md)

## License

MIT. See [LICENSE](LICENSE).
