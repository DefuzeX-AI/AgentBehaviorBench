# 添加 Agent

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | 中文 | [한국어](How%20To%20Add%20Agent.ko.md)

按 **环境 → 导入源码 → 生成配置 → 静态审核 → local 冒烟测试 → KUMA → view → 交付或认证**
执行。所有命令默认在本次 ABB 仓库根目录、已激活的虚拟环境中运行。把 `SOURCE`、
`AGENT_ID`、`NN-name` 和结果路径替换为本次命令实际输出的值。

Coding agent 应先读 `AGENTS.md`、接入 issue 和上游安装说明，记录任务范围、当前仓库和
`git status`，保留无关改动。不能只根据 README 宣称上游可运行。

**什么时候停：**用户要求逐步确认时，每阶段报告命令、结果、证据路径和下一步，等待同意；
否则在已授权范围内继续，不要每个检查点都重新索要许可。开始新的付费或外部操作前，确认
授权已覆盖模型调用，以及向配置的服务发送源码上下文、profile、评测证据；已有授权继续有效。
缺少凭据、必须由用户决定的信息、部署不受支持或失败原因未解决时，停止依赖这些条件的后续
步骤并保留完成的产物。不得输出 key 或 `.env` 内容。检查点要求检查证据，不一定要求询问用户。

## 1. 配置环境

### 安装 ABB 和宿主机依赖

先完成 [ABB 安装](README.zh-CN.md)。需要 Git、Python 3.10+ 和已激活的 venv；
认证还需要当前用户可访问的 Docker。然后安装所选 SDK 的宿主机验证依赖：

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
python -m agentbench --help
python -m agentbench sdk list
docker info
```

`sdk list` 应列出 `kuma`；执行 ABB 的同一用户运行 `docker info` 必须成功。
下载和配置生成不要求 Docker，`-c` 认证需要。宿主机与评测容器中的 SDK 安装相互独立。

配置付费服务前，先验证 harness：

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

预期为 `Case execution: 1/1 completed | Judge: pass=1`，保存实际 `OFFLINE_RESULT=` 路径。
这个确定性 echo demo 不需要 Docker、密钥或模型调用，也不是对目标 Agent 的测试。失败时先修复
宿主环境。检查点报告 checkout 路径/revision、CLI/SDK 发现与 demo 结果。能列出 SDK 不代表支持
接入生成，见第 2 节。

### 配置凭据和模型

只有在 `.env` 不存在时才复制模板：

```bash
test -f .env || cp .env.example .env
```

在本地编辑：

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key**：查询策略目录、生成 Case 和 Judge 所需。ABB 也接受
  `DEFUZEX_API_KEY`，非空 `KUMA_API_KEY` 优先。
- **OpenRouter key 和模型**：用于生成接入文件及运行 Agent。生成模型必须支持
  **严格结构化输出**；普通聊天可用不代表适合生成配置。示例模型名称不是代码的默认值。
- **Agent 依赖**：按目标仓库的说明准备工具 key、数据和外部服务。安装数据库驱动
  不会启动数据库；下载 Agent 也不会自动部署它依赖的全部服务。

凭据获取链接见 [中文配置说明](Guide.zh-CN.md#配置真实评测)。Shell 导出的变量优先于
`.env`，`--env-file PATH` 可选择其他文件。CLI 按声明解析凭据，不把整份 `.env`
挂进容器。不要把真实 key 写进源码或生成的配置文件。

### 按需准备网页

浏览器界面需要 npm，以及 Node.js **20.x 至少 20.19，或 22.12+**：

```bash
cd web
npm ci
npm run build
cd ..
```

这构建的是 ABB 查看器，不会安装 Agent 自己的浏览器或 Node/MCP 依赖。
不需要网页时，在下面的添加命令加 `--no-view`；无界面执行不要求 Node 或 `web/dist`。

## 2. 先导入源码，再生成配置

先只导入源码，在调用模型前留出审核点：

```bash
python -m agentbench agent add https://github.com/owner/repository
```

`SOURCE` 是 HTTPS 仓库地址本身，不能是文件或 `/tree/branch` 页面；也可以是本地绝对目录，
例如 `/absolute/path/to/local-agent`，PowerShell 可用 `C:\work\local-agent`，不需要 `-d`。
GitHub 导入默认分支 revision，目前没有 `--revision`。本地导入排除 `.git`，记录内容的
SHA-256 摘要；同一规范化来源再次调用会复用单元，不会从已变化的本地目录重新覆盖源码。

**检查点——导入完成：**记录实际单元路径和 `source-manifest.json` 的 revision；阅读原入口、
提示词、工具、输入/状态结构、UI 调用方式、Python 约束和锁文件。确认外部服务与部署接口：
文字 graph 不等于 PDF 上传界面。导入不代表已注册可运行 Agent；不要跳过官方 `agent add`
直接把替代实现塞进注册表。

明确这些部署问题后，用同一来源生成配置：

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view
```

`-b` 规划、生成、校验文件并注册为 `adapting`，**不会构建 Docker**。KUMA 在规划前查询最新
策略目录，必须核对用途、可用性、精确版本和证据能力，并保留本次快照，不能照抄别的 Agent
的策略 ID。目录查询失败就停下修复凭据或网络，不得凭空填写。

规划要求补充信息时，将事实写入本地 UTF-8 文件后恢复：

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view --answers answers.txt
```

回答真实的文字到原生输入映射、会话生命周期、排除的 UI 功能、服务及依赖，不得编造业务输入。
重试前先看 `build-result.json` 和失败的 `steps/`；完成的文件会保留并重新验证，人工文件冲突
会停止生成。不要清空进度，也不要在原因没变时重复付费请求。

**当前仓库限制：**此版本 `local` SDK 支持评估，但没有接入要求/校验接口。
`add -b --sdk local` 会报 `Selected SDK has no onboarding requirements and validation`。
本仓库应先用 KUMA 生成，再按第 5 节 local 验证；无 KUMA 凭据时停止自动生成。
补充 local 接入能力属于独立代码修改，不能假设另一个 checkout 的修复已存在于这里。

只有已了解部署且获准连续生成、认证，无需中途等待确认时，才使用合并命令：

```bash
python -m agentbench agent add https://github.com/owner/repository -b -c --sdk kuma --no-view
```

`-c` 是构建、运行认证，会产生实际调用费用，不是静态检查，也支持已有人工配置。
目前自动生成支持 LangGraph；不支持的框架不得改名伪装成 LangGraph。

| 参数 | 用途 |
| --- | --- |
| `--sdk kuma` / `--sdk local` | 显式选择；能发现 SDK 不代表它支持接入生成。 |
| `--no-view` | 保存结果，但不自动启动查看器。 |
| `--build-model MODEL` | 配置生成模型，须支持严格结构化输出。 |
| `--model MODEL` | 认证时使用的 Agent 模型。 |
| `--answers answers.txt` | 回答前一次规划的问题。 |
| `--with-observe` | 配合 `-b` 生成 observe 原生输入提示。 |
| `--build-settings settings.toml` | `[build]` 表中的生成配置。 |
| `-y` | 仅在执行已获授权时跳过 CLI 确认。 |

生成模型优先级：`--build-model`、settings `model`、`OPENROUTER_BUILD_MODEL`、
`OPENROUTER_MODEL`。修改预算或重试前查阅
[默认配置（英文）](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)。

## 3. 了解每个文件的用途

Agent 单元位于 `resources/agents/NN-name/`。命令在导入的源码外围生成接入文件，
不需要在运行命令前手写齐全。

```text
resources/agents/NN-name/
├── agent/                   # 导入的上游或本地源码快照
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 自身源码

保存导入的上游或本地源码快照。真实图、推理和工具仍在这里实现。ABB 接入文件放在目录外，
避免接入时悄悄替换原 Agent 的行为。

### `agent.toml` — ABB 如何启动和调用 Agent

声明 ID、框架、源码 revision、镜像构建/启动设置、适配器、输入输出映射、环境和
模型/工具路由。核对入口路径和必需输入。声明路由或变量不会实现工具，也不会启动服务。

### `bindings/*.py` — 原生输入输出与 ABB 的边界

导出同步、无参数的工厂，返回真实可调用 Agent，处理有源码依据的格式转换和生命周期
清理。不能编造答案或用简化 Agent 替代原实现。Python 语法有效不代表图能真正执行。

### `Dockerfile` — 容器内安装什么

安装 Agent 的 Python/系统依赖，复制源码、binding 和配置。检查 CPU 架构、解释器、
可写位置及 Agent 专属浏览器/Node 需求。当前 KUMA overlay 用 `python -m pip`
安装 SDK，因此该解释器需要支持 pip。

### `.dockerignore` — 哪些文件不进入构建

排除凭据、宿主机 venv、缓存和结果，同时保留镜像必需的源码与配置。
`-b` 使用 ABB 模板生成此文件。

### `requirement.md` — 评测什么

描述已部署 Agent 的用途、可观察行为、真实工具和限制。KUMA 要求 YAML front matter，
以及 Production Use Scenario、Behaviors to Test、Known Limitations or Prohibited
Behaviors 三个章节；策略组从当前 SDK 目录选取。

写当前能力，而非潜在扩展。只有搜索工具的 Agent 能解释计算，但不能执行采样器或保存
文件。明确缺少能力/输入时应该怎样处理。Profile 指导评测，不会增加工具、改变系统提示
或修改已保存的 Case。

### `evaluation/` — 可选支持文件

仅在 Profile 引用 schema 或 fixture 时需要，不强制存在，也没有必需的
`input-contract.json`。当前官方 KUMA 生成路径接受文本；结构化 schema 在本地能解析
不代表远端支持。原生映射仍由 agent.toml 和 binding 负责。

### 注册表和自动记录

`resources/registry.toml` 位于单元之外，保存路径、启用状态、adapting/ready 和 `case`
数量。生成完成登记 adapting，认证控制晋升，`run` 选择启用且 ready 的 Agent。

导入器还会**自动创建 `source-manifest.json`**，记录 GitHub URL 或规范化本地路径及
revision，以便复用导入结果。
它是 ABB 内部记录，不是 KUMA 要求的文件，也不需要用户准备。继续添加流程时保留它。

生成记录位于 `cache/onboarding/<unit-name>-<path-digest>/`：build-state.json 跟踪
可复用工作，各 attempt 保存计划、SDK 目录、steps 和 build-result.json。这些也是
自动记录，不是 Agent 源码。

## 4. 执行前审核与静态校验

**检查点——配置完成：**逐个检查生成文件，不能只看成功提示。核对源码来源和以下边界：

- 描述文件必须指向原始 graph。上游缺少 `langgraph.json` 时，可补最小描述文件（如
  `abb-langgraph.json`），但必须在来源记录中注明本地新增，不能改写 graph。
- binding 导出同步、无参数工厂并调用真实 Agent，传递 `config`/callbacks、异常和原始输出；
  按上游 UI 的消息追加与 active-agent 机制维护会话，隔离 Case，close 时清理。
  不得用全局可变会话状态，也不能吞掉失败。
- manifest 输出字段应提取真实回复，证据保留完整状态。文本映射必须真实；无法提供的多个
  必填业务字段属于停止条件。
- 用兼容解释器安装上游锁文件；宿主 ABB 依赖与 Agent 依赖分开。uv 的 project 路径、锁文件
  和运行解释器必须一致；独立 `/opt/venv` 可避免安装到只读源码树。运行解释器须支持 pip。
- 检查**应用 SDK overlay 后的有效配置**，包括追加路由、binding/runtime 的 COPY 路径。
  只验证外层 TOML 不够。
- profile 写真实工具、调用方必须提供的数据和不可用操作。当前 KUMA 生成要求
  `input_type: text`、三个精确的英文章节标题以及来自目录的策略组。
  未实现的浏览、上传、代码执行、文件持久化不能声明为能力。

人工修正后，调用接入流程使用的静态校验器：

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
unit = Path("resources/agents/NN-name")
print(validate_unit(unit, plugin))
PY
```

此命令离线检查文件和已安装 SDK 的解析规则，不执行 Agent；没有传入目录上下文时，也不会
刷新或校验实时策略选择。生成流程使用保存的最新快照校验，KUMA 运行预检还会检查服务规则。
静态通过不等于执行通过。复杂 binding 应有针对性的离线测试：实际 adapter 边界、会话隔离、
config 传递、支持时的异步路径及异常。fixture 应自包含，缺少可选 Agent 时明确跳过。

## 5. 运行一个 local 冒烟 Case

已配置的文字 Agent 先小规模运行：

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

这里运行真实 Docker Agent 和模型拦截，使用固定文本 Case 与 local Judge。需要 Docker 和
模型配置，可能消耗模型费用；不需要 KUMA 凭据或额度。它与零凭据离线 echo demo 不同。
固定 Case 不由 profile 生成，不保证覆盖文章处理或专家交接。

**检查点——local：**保存 Suite 路径、详细运行目录、回复、轨迹状态和 Judge 报告；只有执行
成功且宿主接受结果后，才能报告接入可运行。第一次运行后打开 view（第 7 节），失败也要看。
导入检查和 fixture 测试不能替代真实执行。

若通用 Case 缺少必要上下文，可在授权后用真实原生输入执行 `observe`。文字 binding 的
`native-input.json` 是 JSON 字符串；其他 binding 按实际 schema。必须提供文章正文或所需
业务数据，不能只写“阅读已提供的文章”却没有正文。

```bash
python -m agentbench observe AGENT_ID --input native-input.json
```

observe 记录原生执行，不调用 KUMA Case/Judge；模型和工具仍可能收费。专项观察不会把失败
benchmark 改为通过。用户明确要求直接 KUMA 时，可在静态审核后进入第 6 节，并如实说明
local 未执行（如果跳过）。

## 6. 发起新的 KUMA 评估

检查部署的 profile 和当前策略，确认 KUMA/模型调用及证据发送已获授权，再运行一个 Case：

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

local 通过不代表 KUMA 兼容；修改 profile 只影响未来 Case。检查生成输入是否提供必要数据、
是否要求部署不具备的操作。将 Case 缺陷与 Agent 问题一起保留，不得改原输入、输出或 Judge
证据来制造通过结果。

等待时跟踪同一次运行的生成、Agent 调用、提交和 Judge 轮询。异步请求被接收不代表已有判定；
轮询期间不要重复发起评估。超时或报错先看保存的完成/恢复状态，再决定恢复或重试。遵守回放
安全限制和工具副作用约束，不得改安全标志强行恢复。新 `evaluate` 创建新 Suite，通常生成新
Case，不是对旧 Case 的受控重跑。

## 7. 打开 view，分开判断不同结果

第一次 local 后、KUMA 后，以及诊断失败、重试或汇报完成前，都应打开查看器。
无界面环境则检查相同的 JSON/轨迹文件，并说明没有进行 UI 审阅。

```bash
python -m agentbench view results/suites/ACTUAL_SUITE_ID/events.json
```

使用命令实际打印的 `Result saved` / `Open later` 路径；offline demo 打印的是带时间戳的
`OFFLINE_RESULT` 文件。不能猜文件名或误用旧 Suite。打开完整 `View:` URL（含路径），保持
服务运行，结束时 Ctrl+C。`--no-view` 不会丢弃结果。

按 **Suite → Case → 逐步输入和回复 → 模型/工具/交接轨迹 → Judge 及证据 → 执行/清理/宿主接受**
检查。比较 Agent 声明与工具实际动作：“交接成功”不等于“专家任务完成”；文字声称写入不等于
真实写入。

| 证据 | 解释与下一步 |
| --- | --- |
| 执行成功 + 宿主接受 + Judge pass | 本 Case 通过；记录覆盖范围，不推广到所有能力。 |
| 执行成功 + 宿主接受 + Judge issue | 接入执行成功；保留行为问题，不为完成接入而改提示词刷通过。 |
| 原生异常 / execution failed | 即使收到 Judge，也不是成功执行；晋升前先诊断。 |
| 部分轨迹 / insufficient evidence / 宿主拒绝 | 单独报告证据缺口；OTel complete 不等于记录了全部工具内容。 |
| 缺少文章/数据或要求不可能的操作 | 记录 Case/profile 限制，另行判断有依据的 Agent 声明；不能编造数据。 |

详细产物在 `results/observe/<run-id>/`，按实际存在情况检查 `run.json`、
`evaluation/case.json`、`evaluation/inputs/`、`evaluation/manifest.json` 和
`evaluation/judge/report.json`。文件缺失可能意味着阶段未完成，不能假定已有判定。
命令非零退出可能是 Judge issue，不一定是程序崩溃。JSON 导出也不是独立完整轨迹归档。

## 8. 决定是否需要认证

`evaluate` 不晋升注册表，也不改变 Case 数量。如果目标包括被 `run` 选中，先核对注册表数量，
确认额外执行已获授权，再运行：

```bash
python -m agentbench certify AGENT_ID --sdk kuma --no-view
```

certify 按配置数量重新执行 Case，不是批准已有评测文件。所有请求的 Case 无调用错误地完成，
可将 `adapting` 晋升到 `ready`，即使 Judge 有行为问题。已 ready 的 Agent 会直接返回，不重新
认证；后续变更用 evaluate 验证。不得手改 ready 隐藏执行阻塞。若用户接受成功评估即完成接入，
报告实际注册状态后停止，不要仅为改变标签额外发起付费认证。

## 9. 在失败的边界诊断

从第一处失败及保存证据入手，尽可能离线最小重放，每次只改变一个因素：原始 graph/binding、
单工具/多工具调用、同步/异步、锁定依赖/宿主环境。诊断脚本放在分发单元外。区分部署修复与
上游行为修改，后者单独提出；不得关闭拦截、隐藏异常或编造成功的工具结果。

| 现象 | 检查、处理与停止条件 |
| --- | --- |
| 找不到 agentbench 或导入了别的 checkout | 激活当前 venv，使用 `python -m agentbench`，先检查 editable 安装，不急于改 Agent。 |
| Docker 不可用、权限不足、镜像架构不匹配 | 同一用户检查 `docker info` 和镜像平台，取得环境所需权限，不绕过隔离。 |
| SDK 已列出但没有 onboarding 接口，或无法 import kuma | 发现 SDK 不等于能力/依赖校验；选支持生成的 SDK，安装固定版本要求。 |
| 策略目录、认证或网络失败 | 检查凭据是否配置、shell 优先级、服务地址和网络，不输出密钥；解决前停止生成。 |
| 结构化输出拒绝、needs_input、文件冲突 | 看计划和逐文件记录，选择支持的生成模型、补真实答案或审核修正文件；只重试受影响阶段。 |
| uv project/锁文件不匹配、缺 pip、容器导入失败 | 检查上游 Python 范围、锁文件位置、解释器、依赖隔离、COPY 路径；静态通过不能证明安装成功。 |
| 外层 TOML 正常但 overlay 报错 | 空 `tool_routes = []` 可能与追加的 `[[llm_interception.tool_routes]]` 冲突；核对有效配置后省略无必要的空声明，保留必需路由和拦截。 |
| 多专家交接报 INVALID_CHAT_HISTORY | 核对每个 AI tool-call ID 是否有对应 ToolMessage，离线重放原 graph；单交接成功不代表并行交接可用，保留上游失败。 |
| Judge 指出没有恢复或声称执行外部动作 | 检查模型是否收到之前的错误，以及相应工具是否存在、是否调用；分开文本声明、运行状态和证据限制。 |
| 查看器空白、打不开、显示旧结果 | 构建 web/dist，使用打印的完整 URL 与准确结果文件，保持进程运行并检查端口权限；不要为修查看器重跑付费评估。 |

Article Explainer 接入体现了这些区别：普通 local 对话可运行，一轮 KUMA 触发原生并行交接
错误，另一轮执行完成但有行为问题；Case 还缺少文章正文。这些只是诊断实例，不能保证其他
revision、模型或 Case 得到相同结论，也不能未经目录审核照搬当时的策略 ID。

## 10. 交付清单与完成汇报

报告源码/revision、单元路径、生成文件与人工修正、执行命令、真实产物/view 路径；分别列出
local/KUMA 执行、宿主接受、Judge、未测能力、已知失败、注册表状态和 Git 状态（是否提交、
推送、PR，或仅本地）。代码/文档改动与 `.venv`、凭据、镜像、缓存、锁文件、结果分开，不提交秘密。

约定的接入目标已有证据就停止。行为问题可能是有效的 benchmark 结果，不代表接入未完成。
不要反复运行碰运气刷通过，也不要悄悄修复被测 Agent。需要提交或 PR 时，作为另一个已授权
步骤准备可审阅改动。

更多内容：[故障排查（英文）](../Troubleshooting.md)、[已知问题（英文）](../Documentation-Issue-Audit.md)、
[生成器实现（英文）](../../agentbench/onboarding/build_agent_env/README.md)。
