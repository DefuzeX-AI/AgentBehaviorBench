# 新增 Agent

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | [简体中文](How%20To%20Add%20Agent.zh-CN.md) | 繁體中文 | [한국어](How%20To%20Add%20Agent.ko.md)

依 **環境設定 → 執行新增命令 → 了解產生的檔案** 順序操作。使用者或 coding agent
都能採用相同流程。除非命令切換目錄，均在 ABB 儲存庫根目錄執行。

## 1. 設定環境

### 安裝 ABB 與主機相依套件

先完成 [ABB 安裝](README.zh-TW.md)。需要 Git、Python 3.10+ 與已啟用的 venv；
認證需要目前使用者可存取的 Docker。接著安裝所選 SDK 的主機驗證相依套件：

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

`sdk list` 應列出 kuma；執行 ABB 的同一使用者必須能成功執行 docker info。
下載及設定產生不需要 Docker，`-c` 認證需要。主機與評測容器的 SDK 安裝相互獨立。

### 設定憑據與模型

僅在 .env 不存在時複製範本：

```bash
test -f .env || cp .env.example .env
```

在本機編輯：

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key**：取得策略目錄、產生 Case 與 Judge 所需。ABB 也接受 DEFUZEX_API_KEY，
  非空的 KUMA_API_KEY 優先。
- **OpenRouter key 與模型**：用於產生接入檔案及執行 Agent。產生設定的模型必須支援
  **嚴格結構化輸出**；能聊天不代表適合此用途。範例模型名稱不是程式的隱含預設值。
- **Agent 相依需求**：依上游說明準備工具 key、資料與外部服務。安裝資料庫驅動不會
  啟動資料庫；下載 Agent 也不會自動部署所有服務。

憑據連結見 [設定指南（英文）](../../README.md#configure-a-real-evaluation)。Shell 匯出
變數優先於 .env；可用 --env-file PATH 指定另一個檔案。CLI 依宣告解析憑據，
不把整份 .env 掛入容器。不要將真實 key 寫入原始碼或產生的設定檔。

### 視需要準備網頁

需要 npm，以及 Node.js **20.x 至少 20.19，或 22.12+**：

```bash
cd web
npm ci
npm run build
cd ..
```

這建置 ABB 檢視器，不會安裝 Agent 自己的瀏覽器或 Node/MCP 相依套件。
不需網頁時，在新增命令加 --no-view；無介面執行不要求 Node 或 web/dist。

## 2. 執行新增命令

將 URL 換成 Agent 的 GitHub 儲存庫網址，不使用檔案或 /tree/branch 頁面網址：

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`：產生並驗證接入檔案，登記為 adapting，不代表立即建置 Docker 映像。
- `-c`：透過認證流程建置並執行 Agent。設定的 Case 執行驗收成功後成為 ready，
  Judge 仍可能回報行為問題。

ABB 下載原始碼、規劃接入、逐檔儲存驗證結果，再詢問是否認證。產生與認證可能收費。
目前自動設定支援 **LangGraph**；其他框架需要先有對應的介接器支援。

想先檢查產生的檔案，省略 -c：

```bash
agentbench agent add https://github.com/owner/repository -b
```

兩個參數都省略時，agentbench agent add URL 只下載並列出設定檔，不產生接入設定，
也不登記可執行 Agent。下載器記錄預設分支的 revision，目前沒有 --revision 選項。

| 參數 | 用途 |
| --- | --- |
| `--no-view` | 認證不啟動網頁，仍儲存結果。 |
| `--build-model MODEL` | 接入檔案產生模型。 |
| `--model MODEL` | 認證時 Agent 使用的模型。 |
| `--answers answers.txt` | 以文字檔回答前次規劃的問題。 |
| `--with-observe` | 配合 -b 產生 observe 的原生輸入提示。 |
| `--build-settings settings.toml` | 以 [build] 表覆寫產生設定。 |

模型優先序：--build-model、settings 的 model、OPENROUTER_BUILD_MODEL、
OPENROUTER_MODEL。更改預算、逾時或重試前，先看
[預設設定](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)。

## 3. 了解每個檔案的用途

Agent 單元位於 resources/agents/NN-name/。命令會在下載的原始碼周圍產生接入檔案，
不需要執行前手動準備齊全。

```text
resources/agents/NN-name/
├── agent/                   # Downloaded upstream source
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 自身原始碼

保存下載的上游儲存庫，真實的圖、推理與工具仍在此實作。ABB 接入檔案放在目錄外，
避免接入時暗中替換原 Agent 行為。

### `agent.toml` — ABB 如何啟動與呼叫 Agent

宣告 ID、框架、來源 revision、映像建置/啟動、介接器、輸入輸出映射、環境及模型/
工具路由。核對入口路徑與必要輸入。宣告路由或變數不會實作工具或啟動服務。

### `bindings/*.py` — ABB 與原生輸入輸出的邊界

匯出同步、無參數的工廠，回傳真實可呼叫 Agent，處理有原始碼依據的格式轉換及生命
週期清理。不能捏造答案或用簡化 Agent 替代。Python 語法有效不代表圖能執行。

### `Dockerfile` — 容器內安裝內容

安裝 Python/系統相依套件並複製原始碼、binding 與設定。檢查 CPU 架構、解譯器、
可寫位置與 Agent 專屬瀏覽器/Node 需求。目前 KUMA overlay 用 python -m pip 安裝
SDK，因此選用的解譯器需要支援 pip。

### `.dockerignore` — 排除建置內容

排除憑據、主機 venv、快取與結果，保留映像必需的原始碼和設定。-b 由 ABB 範本產生。

### `requirement.md` — 評測內容

描述已部署 Agent 的用途、可觀察行為、真實工具及限制。KUMA 要求 YAML front matter
和 Production Use Scenario、Behaviors to Test、Known Limitations or Prohibited
Behaviors 三個章節；策略群組從目前 SDK 目錄選取。

描述現有能力，而非未來擴充。只有搜尋工具的 Agent 能解釋計算，不能執行取樣器或
儲存檔案。明確說明缺少能力/輸入時如何處理。Profile 指導評測，不新增工具、不改
系統提示，也不修改已儲存的 Case。

### `evaluation/` — 選用支援檔案

僅在 Profile 引用 schema 或 fixture 時需要，不強制存在，也不要求 input-contract.json。
目前官方 KUMA 產生流程接受文字；本機能解析結構化 schema 不代表遠端支援。
原生映射仍由 agent.toml 與 binding 負責。

### 登錄表與自動記錄

resources/registry.toml 位於單元外，保存路徑、啟用狀態、adapting/ready 與 case 數。
產生完成登記 adapting，認證控制晉升，run 選擇啟用且 ready 的 Agent。

下載器會**自動建立 source-manifest.json**，記錄儲存庫與 revision 以重用下載。
它是 ABB 內部記錄，不是 KUMA 要求的檔案，使用者無須準備。繼續新增流程時保留它。

產生記錄另存於 cache/onboarding/<unit-name>-<path-digest>/。build-state.json 追蹤
可重用工作；各 attempt 保存計畫、SDK 目錄、steps 和 build-result.json。
這些也是自動記錄，不是 Agent 原始碼。

## 產生之後

只使用 -b 時，準備符合 binding 的 JSON 輸入，接著檢查原生執行並認證：

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

使用產生的 Agent ID。observe 不呼叫 KUMA Case/Judge，但模型與工具仍可能收費。
evaluate --cases 1 不改登錄表數量，certify 使用該數量，執行前先檢查。
已 ready 的 Agent 不會再次認證；後續更改使用 evaluate 驗證。

產生停止時，讀取 build-result.json 與失敗步驟，修正後重跑相同的 -b 命令。
已完成檔案保留並重新驗證，手動檔案衝突會停止而不覆寫。規劃需要補充資訊時使用
--answers answers.txt。

依賴、部署、Trace/Judge 與恢復問題見 [故障排查（英文）](../Troubleshooting.md) 和
[已知問題（英文）](../Documentation-Issue-Audit.md)。實作細節見
[開發者指南（英文）](../../agentbench/onboarding/build_agent_env/README.md)。
