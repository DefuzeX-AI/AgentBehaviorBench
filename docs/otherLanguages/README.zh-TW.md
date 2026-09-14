# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — 羊駝 Agent 工作流程審查" src="../figures/title.png" width="720" style="border-radius: 24px;">
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
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **執行 ABB 前請先準備：**Python 3.10+、已啟動的 Docker Desktop 或 Docker
> Engine。KUMA 會在建置評測容器時自動從 PyPI 安裝。Company Research Agent 需要
> `KUMA_API_KEY`（或 `DEFUZEX_API_KEY`）、`OPENROUTER_API_KEY`、
> `OPENROUTER_MODEL` 與 `TAVILY_API_KEY`。

AgentBehaviorBench 會在隔離執行環境中執行已註冊的 AI Agent、收集執行證據，並以
可選 SDK 評測結果。預設 SDK 是內建 KUMA adapter；結果儲存在本機，可用 ABB 瀏覽器
檢視器查看。

![AgentBehaviorBench 執行架構](../figures/framework.png)

## 快速開始

在儲存庫根目錄建立虛擬環境，並安裝 ABB：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

建立本機環境檔案並填入憑證：

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

啟動 Docker 後，執行所有 registry 中 `enabled = true` 且狀態為 `ready` 的 Agent：

```bash
agentbench run
```

ABB 會要求確認選取的 Agent，在 `results/` 下儲存結果快照並啟動本機檢視器。無介面
或自動化執行請使用：

```bash
agentbench run --no-view --output results/benchmark.json
```

## 相依條件與環境變數

| 項目 | 用途 |
| --- | --- |
| Python 3.10 或更新版本 | ABB 主機 CLI 與 harness。 |
| Docker Desktop / Docker Engine | 目前可執行的內建 Agent 在 Docker 中運行；執行前 Docker 必須已啟動。 |
| `KUMA_API_KEY` 或 `DEFUZEX_API_KEY` | 預設 KUMA SDK 的 Case 與 Judge 存取憑證。 |
| `OPENROUTER_API_KEY` | Docker Agent 的模型流量經 ABB interceptor 轉送至 OpenRouter。 |
| `OPENROUTER_MODEL` | 此次執行使用的模型名稱。 |
| `TAVILY_API_KEY` | 內建 Company Research Agent 的網頁搜尋憑證。 |

`.env` 不會被 Git 追蹤。Shell 已匯出的變數會覆寫 `.env`；`--env-file PATH` 可選擇
其他 dotenv 檔案；`--model MODEL` 可只覆寫單次命令的模型。

可選 OpenRouter 設定：

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

執行 `agentbench --help` 或 `agentbench <command> --help` 檢視已安裝版本的說明。

| 命令 | 用途 |
| --- | --- |
| `agentbench run` | 評測所有啟用且 `ready` 的 Agent；這是預設命令。 |
| `agentbench evaluate company-research-agent --cases 1` | 以指定數量的獨立 Case 評測一個 Agent。 |
| `agentbench observe company-research-agent` | 使用原生輸入執行一個 Agent 並保存 trace，不建立 Case，也不呼叫 Judge。 |
| `agentbench certify react-agent` | 認證 `adapting` Agent；成功後將其升為 `ready`。 |
| `agentbench view results/benchmark.json` | 在本機檢視器重新開啟結果。 |
| `agentbench sdk list` | 列出內建與已安裝的評測 SDK。 |
| `agentbench clean --dry-run` | 預覽將移至可復原封存的本機結果歷史。 |

常用 `run` 選項：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

完整參數請見英文 [CLI reference](../docs/CLI.md)，新增 Agent 請見
[agent onboarding guide](../docs/How%20To%20Add%20Agent.md)。

## 目錄結構

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

- `resources/registry.toml` 宣告 Agent、狀態與執行環境。
- `resources/agents/` 儲存每個 Agent 單元及其 ABB 設定。
- `agentbench/cli/` 提供命令列入口。
- `agentbench/harness/` 負責 suite 執行、結果與 registry 載入。
- `agentbench/runtime/` 在本機或 Docker 中執行 Agent。
- `agentbench/sdk/plugin/` 包含內建 SDK adapter 與插件探索邏輯。

## 開發

```bash
python -m pytest
```

儲存庫規範見 [AGENTS.md](../AGENTS.md) 與 [docs/AGENTS.md](../docs/AGENTS.md)。

## 授權

MIT，見 [LICENSE](../LICENSE)。
