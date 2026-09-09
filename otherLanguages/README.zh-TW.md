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
  <a href="README.zh-CN.md">中文简体</a> |
  中文繁體 |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## 最新動態

- AgentBehaviorBench (ABB) 現在會透過 DefuzeX SDK 的 `get_input()` / `submit()` 握手流程，執行已註冊的 LangGraph Agent。

## 概覽

AgentBehaviorBench (ABB) 是一套用於評估 AI Agent 的 benchmark，面向需要呼叫目標 Agent、收集其輸出和執行 trace，並判斷其是否正確完成指定 workflow 的端到端任務。

給定一個已註冊的 Agent 和一個 benchmark Case，AgentBehaviorBench (ABB) 會透過受信任的 host harness 執行該 Agent。這個 harness 可以啟動特定 framework 或容器化的 Agent，透過 credential-safe 的 Model Interceptor 路由 model traffic，將每個 SDK input 和 Agent response 記錄為 原子更新的 JSON events，並把完成的 run 提交給 DefuzeX Judge。

AgentBehaviorBench (ABB) 旨在讓 Agent 評估具備可重現性。Agent 會在 registry 中宣告，透過 LangGraph 等 framework adapters 接入，從 `adapting` 認證到 `ready`，並且只有在認證成功後才會被納入預設 benchmark runs。

目前的執行流程如下：

```text
registry.toml
-> SuiteRunner
-> BenchmarkRunner
-> DefuzeX SDK Run
-> Agent Adapter / Runtime
-> Judge Report
```

此 repository 包含：

- `agentbench/cli`：terminal entry point 和 progress output。
- `agentbench/harness`：SDK handshake、suite execution、results 和 registry。
- `agentbench/adapter`：framework-neutral 的 adapter contract 和 LangGraph support。
- `agentbench/runtime`：local 和 Docker runtime integration。
- `resources/agents`：可重現的 benchmark agent fixtures。
- `services/model-interceptor`：Docker runs 中用於 model provider access 的透明攔截服務。

![AgentBehaviorBench (ABB) framework](../figures/framework.png)

## 安裝

AgentBehaviorBench (ABB) 需要 Python 3.10 或更高版本，以及 DefuzeX Python SDK。SDK 提供 AgentBehaviorBench (ABB) 使用的 benchmark protocol：解析 benchmark requirements、建立 DefuzeX Cases、驅動每個 SDK input、記錄 evidence，並提交完成的 runs 進行 judging。

在包含此 repository 的 parent workspace 中建立並啟用 virtual environment：

```powershell
cd <workspace-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

以 editable mode 安裝 AgentBehaviorBench (ABB)：

```powershell
python -m pip install -e .\defuzeX_AgentBench
```

### 內部 SDK 建置

此 repository 目前依賴內部 DefuzeX SDK 的 `dev` branch。在 SDK 支援一般 package installation 之前，如果 `Defuze-SDK` 尚未 clone 到本機，請從 SDK `dev` branch（`https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev`）clone 到 `defuzeX_AgentBench` 旁邊，然後安裝到同一個 `.venv`：

```powershell
cd <workspace-root>
git clone --branch dev --single-branch https://github.com/DefuzeX-AI/Defuze-SDK
python -m pip install -e .\Defuze-SDK
python -m pip install -e .\defuzeX_AgentBench
```

典型的 source checkout 會把 `Defuze-SDK` 和 `defuzeX_AgentBench` 作為同一個 parent workspace 下的 sibling directories，並將兩者都以 editable mode 安裝。

> [!NOTE]
> PAT 表示 Personal Access Token。如果內部 DefuzeX SDK repository 是 private，GitHub 可能會在透過 HTTPS clone 時要求 PAT。請把 PAT 當作 password 處理：不要把它寫入 source files、README examples、notebooks 或已提交的 `.env` files。

## 使用

安裝 AgentBehaviorBench (ABB) 後，從 benchmark workspace 使用 launcher script 啟動：

```powershell
cd <workspace-root>
.\.venv\Scripts\Activate.ps1
python .\run_agentbench.py
```

也可以直接從 AgentBehaviorBench (ABB) repository 執行 package：

```powershell
cd <workspace-root>\defuzeX_AgentBench
python -m agentbench
```

如需儲存一次 run 並在 local result viewer 中檢視 live benchmark events，請傳入 output path：

```powershell
python -m agentbench --output results\result.json
```

不傳 `--output` 時，AgentBehaviorBench (ABB) 會在 terminal 中執行，且不會建立 JSON result artifact。傳入 `--output` 時，AgentBehaviorBench (ABB) 會寫入一個 原子更新的 JSON result file，並啟動 local viewer，讓你可以在 benchmark 執行期間重新整理並檢查 events。

使用 official Case 或 Judge providers 時，請設定 DefuzeX API key：

```powershell
$env:DEFUZEX_API_KEY = "dfx_<public-id>.<secret>"
```

執行 test suite：

```powershell
python -m pytest
```

更多面向 Agent 的說明，請從 [AGENTS.md](../AGENTS.md) 開始。更完整的 documentation guide 位於 [docs/AGENTS.md](../docs/AGENTS.md)。

## 如何新增待測 Agent

如果你想把自己的 Agent 加入 benchmark，請讓 agent 閱讀 [docs/How To Add Agent.md](../docs/How%20To%20Add%20Agent.md)，並按照其中記錄的 onboarding flow 操作。

AgentBehaviorBench (ABB) 提供了把 external Agent project 轉換為 repeatable benchmark target 所需的元件：registry-based discovery、framework adapters、Docker runtime support、透過 Model Interceptor 路由 model credentials、原子更新的 result artifacts、local result viewing，以及從 `adapting` 到 `ready` 的 certification。這讓你可以用同一組 DefuzeX Cases 一致地比較不同 Agent，同時讓 runtime behavior、outputs 和 judgment evidence 保持可檢查。

## 引用和授權

MIT License。見 [LICENSE](../LICENSE)。

如果你覺得我們的工作有幫助，請按如下方式引用：
