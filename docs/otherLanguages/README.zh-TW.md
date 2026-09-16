# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — 羊駝 Agent 工作流程審查" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
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
> Engine，以及用來建置結果檢視器的 Node.js 20.19+ 或 22.12+。KUMA 會在建置評測容器時
> 自動從 PyPI 安裝。兩個內建 Agent 都需要 `KUMA_API_KEY`（或 `DEFUZEX_API_KEY`）、
> `OPENROUTER_API_KEY`、`OPENROUTER_MODEL` 與 `TAVILY_API_KEY`。

AgentBehaviorBench 會在隔離執行環境中執行已註冊的 AI Agent、收集執行證據，並以
可選 SDK 評測結果。預設 SDK 是內建 KUMA adapter；結果儲存在本機，可用 ABB 瀏覽器
檢視器查看。

![AgentBehaviorBench 執行架構](../figures/framework.png)

首次執行遇到錯誤時，請先看下方的[疑難排解](#疑難排解)。

## 快速開始

在儲存庫根目錄建立虛擬環境，並安裝 ABB：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

結果檢視器由 `web/` 建置，儲存庫中不包含建置產物。開啟結果前先建置一次；`run`、
`evaluate`、`certify` 結束後會啟動它，`agentbench view` 可重新開啟已儲存的結果：

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
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

`KUMA_API_KEY` 是 KUMA SDK 文件使用的變數名稱；ABB 也接受別名 `DEFUZEX_API_KEY`，僅在
`KUMA_API_KEY` 為空時使用。`OPENROUTER_MODEL` 必須設定且沒有預設值，上面的值只是範例，
請換成你的帳戶可用的模型。

啟動 Docker（`docker info` 應能成功）。納入版本控制的 registry 啟用了兩個 Agent，狀態都是
`ready`：`react-agent` 與 `company-research-agent`。先評測一個 Case；這會呼叫依金鑰
計費的 KUMA Case 與 Judge 服務：

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

執行所有 registry 中 `enabled = true` 且狀態為 `ready` 的 Agent：

```bash
agentbench run
```

ABB 會要求確認選取的 Agent，在 `results/` 下儲存結果快照並啟動本機檢視器。無介面
或自動化執行請使用：

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

## 相依條件與環境變數

| 項目 | 用途 |
| --- | --- |
| Python 3.10 或更新版本 | ABB 主機 CLI 與 harness。 |
| Docker Desktop / Docker Engine | 內建 Agent 在 Docker 中運行；執行前 Docker 必須已啟動。 |
| Node.js 20.19+ 或 22.12+（含 npm） | 建置一次 `web/` 結果檢視器；無介面執行（`--no-view`）不需要。 |
| `KUMA_API_KEY` 或 `DEFUZEX_API_KEY` | 預設 KUMA SDK 的 Case 與 Judge 存取憑證。兩者都設定時使用 `KUMA_API_KEY`。 |
| `OPENROUTER_API_KEY` | Docker Agent 的模型流量經 ABB interceptor 轉送至 OpenRouter。 |
| `OPENROUTER_MODEL` | 必填的模型名稱。`.env.example` 中的值只是範例，不是執行時的預設值；請選擇你的帳戶可用的模型。 |
| `TAVILY_API_KEY` | 兩個內建 Agent（ReAct 與 Company Research）的網頁搜尋憑證。 |

`.env` 不會被 Git 追蹤。Shell 已匯出的變數會覆寫 `.env`；`--env-file PATH` 可選擇
其他 dotenv 檔案；`--model MODEL` 可只覆寫單次命令的模型。

可選 OpenRouter 設定：

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

執行 `agentbench --help` 或 `agentbench <command> --help` 檢視已安裝版本的說明；這是完整的
參數參考。

| 命令 | 用途 |
| --- | --- |
| `agentbench run` | 評測所有啟用且 `ready` 的 Agent；這是預設命令。 |
| `agentbench evaluate company-research-agent --cases 1` | 以指定數量的獨立 Case 評測一個 Agent。 |
| `agentbench observe company-research-agent` | 使用原生輸入執行一個 Agent 並保存 trace，不建立 Case，也不呼叫 Judge。 |
| `agentbench certify NEW-AGENT` | 認證 `adapting` Agent；成功後將其升為 `ready`。 |
| `agentbench view RESULT.json` | 在本機檢視器重新開啟結果；路徑是執行結束時 `Result saved:` 後印出的檔案（含時間戳記）。需先建置 `web/`，見快速開始。 |
| `agentbench sdk list` | 列出 SDK adapter 目錄，不匯入 SDK 實作。 |
| `agentbench clean --dry-run` | 預覽 `clean` 會移入 `cache/history-trash/` 的 `results/` 下未被參照的項目；不會刪除任何內容。 |

常用 `run` 選項：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

新增 Agent 的完整說明（`agent add`）見[英文 README 的 CLI 一節](../../README.md#cli)（英文），
以及 [agent onboarding guide](../How%20To%20Add%20Agent.md)（英文）。

## 疑難排解

以下是首次執行時 `evaluate`、`run` 或 `certify` 輸出的常見錯誤。除模型名稱一列外，其餘
都在任何 KUMA 請求之前停止，不會計費。

| 輸出 | 原因 | 處理 |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker 未啟動，或 `DOCKER_HOST` 指向不存在的 daemon。 | 啟動 Docker Desktop 或 Docker 服務，直到 `docker info` 成功。 |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | 環境變數與 `.env` 中都沒有 KUMA 憑證。 | 在 `.env` 中設定 `KUMA_API_KEY`。 |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | 變數中放的不是 KUMA 金鑰，例如誤填了 OpenRouter 金鑰。 | 使用為 KUMA 核發的 `dfx_` 金鑰。 |
| `AuthenticationError: Invalid API key.`，之前有 `GET defuzex.ai/… \| HTTP 401` | KUMA 金鑰錯誤、已撤銷，或屬於另一個 Backend。 | 更換金鑰；若設定了 `KUMA_BASE_URL`，一併檢查。 |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | 未設定 `OPENROUTER_MODEL`；ABB 沒有預設模型。 | 在 `.env` 中設定 `OPENROUTER_MODEL`，或傳入 `--model`。 |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY`（或 `TAVILY_API_KEY`） | 模型上游或 Agent 的 `agent.toml` 需要的憑證缺失。 | 將提示中的變數加入 `.env` 或匯出至 shell。 |
| `LLM call 01 \| openrouter \| FAILED`，接著是引用上游訊息的 `related network: upstream_error POST …` | 模型上游拒絕了呼叫，例如模型名稱不存在，或金鑰無權使用該模型。此時 Case 已產生，仍可能被 Judge 並計費。 | 使用上游為你的金鑰列出的模型名稱。 |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | 目前的檢出中尚未建置檢視器。 | 以 Node.js 20.19+ 或 22.12+ 執行提示中的命令。 |

`agentbench clean` 不會刪除任何內容：它列出 `results/` 下未被參照的頂層項目，確認後將其
移入 `cache/history-trash/<時間戳記>/`。已儲存的 Suite 及其參照的產物保持原位。若要復原，先
停止執行與檢視器，再將封存項目移回 `results/`。

## 目錄結構

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

- `resources/registry.toml` 宣告 Agent、狀態與執行環境。
- `resources/agents/` 儲存每個 Agent 單元及其 ABB 設定。
- `agentbench/cli/` 提供命令列入口。
- `agentbench/harness/` 負責 suite 執行、結果與 registry 載入。
- `agentbench/runtime/` 在本機或 Docker 中執行 Agent。
- `agentbench/sdk/plugin/` 包含內建 SDK adapter 與目錄探索邏輯。
- `web/` 是結果檢視器的原始碼；`npm run build` 產生 CLI 使用的 `web/dist`。

執行流程為：`resources/registry.toml` → CLI 選取 → SuiteRunner／評測 SDK →
Agent adapter 與執行環境 → 結果快照與本機檢視器（見上方架構圖）。

## 開發

```bash
python -m pytest
```

儲存庫規範見 [AGENTS.md](../../AGENTS.md)（英文）。

## 授權

MIT，見 [LICENSE](../../LICENSE)。
