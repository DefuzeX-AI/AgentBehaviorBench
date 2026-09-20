# MiniMax → ABB 缺陷清单与解决方案

状态：用户已同意实施；逐项进度见 MiniMax-ABB-Progress.md。日期：2026-09-20。

范围：当前 MiniMax Agent unit、ACP adapter、透明网络观测、KUMA 文件/Trace 证据、Viewer 索引、认证流程。以下列出本次检查已发现的全部问题，不代表未检查路径不存在其他缺陷。

## 1. 已知事实与边界

- 原生 MiniMax 单 Case 单步已有真实 Judge pass/high；其 6 个模型请求/响应全部保存且全部 HTTP 200。
- 这 6 次请求中，4 次执行任务，2 次生成标题；标题请求发生在 ACP prompt_completed 之后。
- 原始网络记录 6/6 有 case_id，0/6 有 framework_span_id。Viewer 的 6 条模型记录均丢失公开 case_id/input_id；筛选 step-1 后变成 0 条。
- 当前安装 `kuma-defuzex[otel]==0.2.7`，SDK 默认 track_files=True、upload_diff=False；ABB 明确覆盖为 track_files=False。
- 本次离线调用 SDK 自带 Snapshotter/compare_snapshots，确认能识别新增、修改并生成 unified diff。该实验验证 SDK 组件，不代表官方提交验收。
- 已保存的后端 judge/config 响应声明了 file_diff；这是那次运行的配置快照，正式验收时必须重新检查。
- 上轮验证为 96 passed、1 skipped，加原生镜像离线握手。不能把这些离线测试记为真实多轮或并发验收。

## 2. 全部已发现问题

| ID | 优先级 / 类别 | 事实与影响 | 对应方案 |
|---|---|---|---|
| D01 | P1 / 已复现代码缺陷 | worker 直接写 result.json，绕过 TraceStore 脱敏；假密钥回显实验可复现。异常、output、raw_output 都可能落盘。尚未证明真实凭据外泄或 SDK 最终对外泄露。 | A |
| D02 | P2 / 已复现代码缺陷 | Viewer 未找到 input context 时把已有 case_id 也置空。结果无法正确展示 Case 归属。 | B1 |
| D03 | P2 / 观测接入缺口 | Python HTTP instrumentation 覆盖不到原生 Node；网络请求缺少精确的 input/turn 关联，step 筛选看不到模型调用。 | B2、B3 |
| D04 | P2 / 分类与展示缺口 | 前台模型调用、后台标题调用、其他 HTTP 请求缺少独立的关联覆盖统计；9/9 uncorrelated 混合了 6 次模型与 3 次其他 HTTP 请求。 | B1、B3 |
| D05 | P2 / SDK 接入缺口 | ABB 关闭文件追踪，也未启用 diff 提交；onboarding_catalog 同样写死 track_files=False。SDK 能力没有接通。 | C |
| D06 | P2 / 目录契约缺口 | SDK repo=/opt/abb-sdk-repo，MiniMax 工作区=/home/agent/workspace。只打开开关会观察错误目录。 | C |
| D07 | P2 / 产物留存缺口 | 工作区最终文件未导出；容器清理后只剩工具记录，不能独立复查最终产物。SDK diff 也不等于完整文件备份。 | C |
| D08 | P2 / Case 质量与验收缺口 | 已有官方 Case 请求不存在的 TypeScript helper，和空工作区能力不匹配；该 Case 无法验证正常代码修改。仅靠 Profile 的自然语言限制不足以确保前置条件。 | D |
| D09 | P3 / 外部可选能力失败 | 标题相关内容审核返回 401/token is required，主模型鉴权正常。可选路由失败被记录，但该原生功能未通过。 | E |
| D10 | P2 / 生命周期待完成 | 注册仍为 adapting，默认 ready 集合不会选中。evaluate 不修改状态，这是当前语义，不能称为状态更新代码坏了。 | F |
| D11 | P2 / 验收覆盖不足 | 缺少真实 MiniMax 多轮、并发 Case 隔离、后台请求跨轮归属和故障恢复的完整验收。 | F |

不列为已确认缺陷：48 个本地 OTel 属性被 SDK allowlist 过滤、internal_model_spans=not_observed、单次 models.dev 客户端断连。这些均有记录；当前 4 个工具 span 的参数和结果完整。不能为让状态变成 complete 而放宽 SDK allowlist，也不能声称已经发生跨 Case 污染。

## 3. A：统一结果持久化与提交的脱敏边界

改动位置：`runtime/agentcontainer/worker.py`、`sdk/common/artifacts.py`、`sdk/plugin/kuma/runner.py`。

1. 在写 result.json 前，复用现有 environment_secrets/redact 的实现，覆盖 output、raw_output、error。原始值只存在执行过程内存，不另写 raw 文件。
2. 提交到 SDK 的 output 使用相同的已清理结果，避免只清理文件而提交旧的内存副本。
3. 独立保存 redaction 状态：是否处理、命中次数、字段路径、规则类型；不保存密钥、密钥片段或可逆替代值。执行状态、stop_reason 不因脱敏被改成成功。
4. KUMA 现有 Artifacts.save 可能在 worker 返回后重写并脱敏 result.json，但这不能消除首次落盘窗口，也不覆盖 standalone observe；修复应落在共享 worker 的首次写入边界。
5. 对内容省略的说明使用 ABB 本地产物及 SDK 已支持的表达，不能随意给官方严格 schema 增加字段。后续文件 diff 的敏感内容由 SDK 自身处理。

验收：假凭据分别进入正常输出、raw_output、异常；所有持久化产物及提交给 SDK 的对象均无明文，普通文字与非凭据字段保持语义；observe/evaluate 两条路径均覆盖。

## 4. B：分层关联，不补造内部模型 span

### B1：保留身份并拆分覆盖统计

改动位置：`observe/interactions.py`、`observe/review.py` 及消费这些数据的 Viewer。

- 独立保留 suite/job/attempt/Case 身份与 input 身份。Case 的来源为宿主已绑定的 attempt context；input 的来源必须另有可核验依据。
- 找不到 input 时，case_id 仍取可信的原始 envelope；禁止递归搜索模型 payload 中任意名为 case_id 的字段来建立权威身份。
- 引入独立的关联状态，例如 case_only、input_exact、ambiguous；字段名称是草案，不能和 HTTP complete/failed 混为一项状态。
- 统计分别展示：HTTP 配对完整性、Case 身份完整性、已确认轮次归属、工具关系覆盖、内部模型 span 可用性；metadata/title/evaluation 流量分别计数。
- 筛选某个 step 时，明确列出已确认请求，同时提供独立的“本 Case 尚未分配轮次的请求”列表及数量。不能把这些请求隐藏成“本轮没有模型调用”，也不能算入该轮 token/时延。
- 旧产物只重建派生索引，不改写 network.jsonl；没有证据的历史轮次仍保持未知。

验收：现有产物的 6 条请求全部保留 Case；HTTP 6/6 与内部 span 0/6 分开显示；step 视图不会静默丢掉未归属请求；伪造在 prompt 文本里的 input_id 不影响身份。

### B2：利用工具 ID 建立明确的关系

增加通用协议提取/关联组件，由现有协议模块负责识别模型响应的工具 ID；Viewer 只消费标准关系。

关系键至少包括 `(artifact_run_id, attempt_id, native_session_id, tool_call_id)` 中可用且已验证的作用域。原始工具 ID 的匹配必须在同一 attempt 内进行；缺失 session 或重复 ID 时保留候选和 ambiguous，不默认唯一。

关系类型：

```text
一次 HTTP 请求 ──call_id──> 对应 HTTP 响应
模型响应 ──当次新产生的 tool_use.id──> ACP 工具调用
ACP 工具调用 ──既有 input_id──> 当前 Input
```

- 现有运行前三次模型响应产生的 1+2+1 个工具 ID，均与 4 个 ACP 工具事件匹配。
- 匹配是“模型响应产生了工具调用”的证据，不能把工具 span 填进 framework_span_id 冒充 LLM span。
- 历史 messages 中的 tool_use/tool_result 只表示引用历史，不足以判断当前请求归属。
- 若响应与工具事件唯一、跨层身份一致，可作为带来源的派生 input 关联；冲突时不分配。
- 同时支持实时索引随响应/工具事件到达而补充关系，及旧产物离线重建；重建规则要版本化。

验收：精确恢复现有 4 个工具关系；两 Case 同名 ID 不混合；同 Case 跨轮历史重放不误配；重试、重复 ID、晚到通知均保持可解释。

### B3：完整轮次关联所需的原生观测接口

仅 B1/B2 无法为所有纯文本和后台请求提供完整的 turn 归属。这一部分必须先验证 MiniMax 的原生扩展/观测接口，不能宣称已有可用配置。

所需最小契约：

```text
ABB invocation_id ↔ ACP prompt ↔ native_turn_id
native_turn_id + purpose ↔ native_request_id ↔ interceptor call_id
```

- 在原生 prompt 被接收时绑定 immutable turn context；在原生模型 transport 发请求时产生唯一 request ID，记录 session、turn、purpose（任务、标题、其他后台操作）和父任务关系。
- 后台任务继承创建时的上下文，不读取一个不断变化的全局 current_input。会话级任务可保持 session-only，不强行指定 input。
- 若使用本地 tracing header 连接 transport 与 interceptor，必须仅用于观测、由 interceptor 消费后移除；验证上游收到的模型、正文、原生认证和其他头不变。追踪标记不能成为授权依据。
- ACP stdout 继续专用于 JSON-RPC，观测事件走独立有界通道；故障明确标注观测不完整，不伪造模型错误。
- 优先使用上游已有公开 extension/plugin/observer。若固定 revision 无此能力，应在上游增加最小观测接口并采用新的固定版本；当前导入的 agent/ 源码不做静默私改。版本变更需要独立审阅与原生行为对比。
- 不推荐通过通用 Node fetch patch 加一个静态 session header：它只能给会话级身份，不能解决标题跨轮或细分 purpose。

验收：两轮连续纯文本调用、第一轮标题延迟到第二轮开始、工具并行、重试、取消后晚到请求均有正确或显式未知的归属；原生响应逐字节透传；内部 LLM span 在真正观测到以前仍为 not_observed。

B3 是完整关联的交付项，B1/B2 完成时只能声明“部分关联缺陷已修复”。

## 5. C：复用 KUMA 文件证据，统一实际评估工作区

### 推荐目录方案

在 Agent evaluation 配置中显式声明评估工作区和初始状态。以下只是拟议配置，现有 schema 尚不支持这些新增项：

```toml
[evaluation.workspace]
path = "/home/agent/workspace"
initial_state = "empty"

[evaluation.file_evidence]
track_files = true
upload_diff = true
export_changed_files = true
```

实现前需统一字段命名并更新 manifest schema、构建规划、验证、文档，不能直接把未知键写进当前 unit。

推荐为此 unit 使用现有 SDK public API：`repo_path=实际评估工作区`、`track_files=True`、`upload_diff=True`。SDK 账本仍位于其根目录下 `.kuma`，由宿主单独持久化，SDK 自身排除它的快照。无需重新实现 snapshot/diff，也无需首先给 SDK 添加另一种 EvidenceCollector。

生成与执行都必须使用相同的初始工作区定义，不能一个观察 MiniMax 实现源码、另一个执行空目录。原生程序、依赖与 bootstrap 继续保留在 `/opt/agent`，不被 SDK mount 覆盖。

- generation 使用工作区初始状态；每个 Case attempt 使用独立新工作区；同 Case 多轮复用该工作区。
- saved Case 通过受控的 `.kuma` 路径注入，保持原始字节、签名、case_id、内容摘要校验。目录迁移不能重写旧 Case 或伪造 provenance。
- 更新 `SDK_REPOSITORY` 使用位置、EvaluationPolicy、host recovery ledger 定位和 generation/export 路径，使它们使用同一解析后的配置；旧 Agent 未声明时保留旧目录行为。
- 旧的已生成 Case 不自动迁移为新工作区 Case：保留原始产物，给出配置不匹配说明；新的正式验收使用匹配工作区定义的 Case。
- 现有 SDK repo mount 只读，不能仅修改 repo_path。需要让实际 workspace 可写，并维持单独的 ledger/输入/证据存储边界。不要把原始工作区直接作为最终可分享的结果目录。

### SDK 参数、能力声明、提交一并接通

改动位置：`sdk/plugin/kuma/configuration.py`、`service.py`、`worker.py`、`runner.py`、`onboarding_catalog.py`、manifest/onboarding 配置。

1. 解析成单一 file evidence 配置，供生成、onboarding capability、执行和验收共同使用；移除多个位置各自写死的布尔值。
2. 使用 SDK `derive_casegen_evidence_capabilities` 生成 `file_change` 等 CaseGen 能力，不手工拼 capability 名称。`file_change` 和 Judge 的 `file_diff` 是不同契约中的名称，不能混用。
3. 启用 upload_diff 时使用 SDK 官方能力协商；后端不支持就给出明确不可用状态，不偷偷降级为只有哈希。
4. SDK 负责每轮 baseline/final snapshot、文件比较、敏感内容过滤和有界 diff。ABB 从 Submission 的 file_evidence/runtime_evidence 导出可查看投影，验证 Judge 收到的实际 envelope，不能只看到本地 diff 就宣称已上传。
5. SDK 快照和 diff 仍有大小/二进制/权限/敏感内容限制。Viewer 分项显示 complete/partial/omitted 与原因，不用整体 trace partial 代替文件证据状态。

### 最终文件留存与查看

- 文件变更列表和 diff 是第一交付项，复用 SDK 已有格式。
- D07 的最终产物另做受控导出：只导出工作区内新增/修改且通过大小、路径、敏感内容检查的文件；不导出 BYOK profile、.kuma、完整 HOME 或凭据。
- 通过后另存 artifact manifest，包含相对路径、状态、尺寸、允许时的哈希和导出/省略原因；删除文件以记录和 diff 表达。
- 导出在容器清理前完成；失败也在 finally 保留已生成的合规证据。不得因导出失败将 Agent 本身的成功改写成行为失败，须单列证据失败。
- 不声称导出了完整文件系统。若需要全部最终项目，则是另一种带显式范围与限额的导出模式。
- Viewer 首版提供文件名/变更类型/脱敏后 diff 文本搜索和前后差异查看；二进制或省略内容有说明。目录 schema 和 UI 路由沿用现有模块，实施时与当前进行中的 Viewer 修改对齐。

验收：3 轮分别创建、修改、删除/重命名；每轮 diff 只覆盖该轮变化；Unicode、二进制、超限、敏感文本、符号链接均给正确结果；两 Case 不共享文件；容器移除后导出产物可查看；SDK ledger/recovery、Case 原始身份和现有 LangGraph 路径保持有效。

## 6. D：Case 前置条件与工作区一致

- 空工作区 unit 的 Profile、生成上下文和工作区初始状态统一为“自包含任务”。
- 需要预置项目的评估改为明确的 fixture/template 定义，在生成前准备并固定内容摘要，在每个 attempt 开始前复制相同版本。不能根据已经生成的 arbitrary Case 临时猜文件并补造环境。
- 优先使用服务提供的结构化前置条件做执行前校验；当前只含自然语言的 Case 不能靠字符串正则可靠证明它是否自包含。
- 检测到明确缺失前置条件时，保留原始 Case 并分类为前置条件/Case 质量问题，避免直接作为 MiniMax 连接故障；不要篡改官方 Judge verdict。
- 将已发生的“缺失 clamp helper”作为反例，以及真实通过的自包含 JSON/Python 任务作为正例。历史 verdict 差异不能被用作单一修复的因果证明。

验收：Case 明确要求的预置文件与 fixture 一致；空工作区有效任务能跑；缺失前置条件可区分；原始报告与 ABB 分类同时可见。

## 7. E：可选标题审核 401

默认保留原生调用并记录 `optional operation unavailable`，展示实际 401/token is required。主模型认证、内容审核认证分开记录。

先核对该固定版本国际站 BYOK 下审核服务的受支持认证方式，再决定补充正式支持的凭据/登录态；不能把模型 Key 生硬转发给另一个服务，也不能伪造审核通过。

若评估范围明确排除标题生成，可采用上游已有 sessionTitle.enabled=false 配置作为单独的 benchmark variant；这会改变被测配置，应记录并重新验收，不能作为默默消除 401 的默认修复。默认方案仍保留原生行为，401 是否能解决取决于服务支持。

验收：可选服务失败不会冒充主模型失败；只有认证配置真实有效且返回成功时才记为已修；否则作为明确的剩余外部限制。

## 8. F：验收与正式准入

保持 evaluate 不更新注册状态的语义。完成补足的验收后，通过现有 certify 流程原子地把 adapting 更新为 ready，不手改字段伪装认证。

建议真实 MiniMax 验收矩阵：

| 场景 | 核验内容 |
|---|---|
| 单 Case 3 轮文件任务 | session 复用、当前输入交付、文件持久化、逐轮 diff、最终文件留存 |
| 单 Case 3 轮纯文本记忆 | 纯文本请求 turn 关联，避免靠工具事件“碰巧通过” |
| 4 个并发 Case，各 3 轮 | session/profile/workspace/request/tool ID 隔离，实际执行有重叠 |
| 第一轮后台标题延迟到第二轮 | 背景请求保留正确来源或明确 session-only，不落到当前前台轮次 |
| 认证失败、429/超时、取消 | 错误不记成成功；清理完整；不自动重放不具 replay_safe 保证的 Case |
| SDK 提交后 Judge 查询中断 | 恢复查询已有判断，不重新运行 Agent |
| 一个已 ready 的 LangGraph 基线 | 既有调用关联、目录、SDK 证据及认证语义无回归 |

故障注入优先使用本地受控服务与真实原生进程，不对线上服务制造压力；明确区分这种结果和真实官方 Judge 验收。实际多轮 Case 需要服务允许，并检查返回的真实步数；max_steps=3 只是上限，不能当成恰好三轮。

技术执行完成、Judge verdict、证据质量、认证状态分开报告。当前 certify 的条件是请求的 Case 全部完成且无执行错误，并不要求每个行为 Judge 都 pass；保持这一点，扩展验收记录而不静默改变准入定义。

## 9. 实施顺序与交付边界

1. **A + B1：** 先关闭结果脱敏缺口并修复已有 Case 身份丢失，产出复现前后对比。
2. **B2：** 建立明确工具关系和透明的覆盖统计；用现有保存产物验证，不消耗模型调用。
3. **C + D：** 接通真实工作区、SDK 文件证据、能力声明、最终文件导出和 Case 初始状态契约。
4. **B3：** 先验证原生观测扩展可行性，形成具体接口及固定版本方案，再完成全请求的 turn/purpose 关联。存在上游依赖时单列，不能把它标为已完成。
5. **E + F：** 核实可选审核服务、执行真实验收矩阵、完成 certify；未解除的外部限制明确留下。

发布验收必须包含原始 Case、Agent 输出、ACP 事件、网络请求、SDK 文件/Trace evidence、Judge report、host acceptance 和 cleanup 结果。每项问题按 ID 关闭，不能以总测试数或单个 Judge pass 代替具体证据。

## 10. 参考位置

- `agentbench/runtime/agentcontainer/worker.py:106`：result.json 首次持久化。
- `agentbench/observe/interactions.py:242`：身份投影。
- `agentbench/observe/correlation.py`、`agentbench/observe/acp.py`：现有网络与协议观测。
- `agentbench/sdk/plugin/kuma/worker.py:69`、`configuration.py`、`service.py`：SDK 参数及目录。
- `agentbench/sdk/plugin/kuma/onboarding_catalog.py:29`：生成侧能力声明。
- `agentbench/cli/features/certify.py:167`：准入更新。
- `cache/acp-acceptance/minimax-review-20260920.md`：调查报告。
- `cache/acp-acceptance/minimax-correlation-audit.py` / `.json`：只读可复核实验。
- `results/observe/b2791572b7e7479fbfb81505df559db4/`：成功运行原始产物。
