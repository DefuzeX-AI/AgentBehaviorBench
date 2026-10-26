# ABB Suite GT 检测实施设计

状态：待实现方案。代码基线为当前 AgentBehaviorBench 工作区。本文中的新增模块、命令、schema 和函数签名均为拟定接口；公共接口表中标记为现有的接口已核对源码。

目标：用 ABB provider 调用语言模型，对一个已生成并执行的完整 Suite 与各 Agent 的 GT 做语义比对，回答哪些缺陷被 Case 触发、哪些被 SDK Judge 正确识别，并保存可追溯、可续跑的结果。

首版交付离线 CLI、KUMA 证据读取、两阶段评审、独立结果存储、汇总和兼容导出。不会重新运行 Agent、生成新 Case 或重新调用 SDK Judge。Suite 完成后的自动触发作为后续接入，共用同一个服务入口。

## 1 目录放置与创建边界

仓库根目录为 `C:/Song_startup/benchmark/AgentBehaviorBench`。下述代码路径均相对该目录。执行结果写入用户指定 Suite，不能默认写到仓库的 resources 或共享 cache。

### 1.1 开发时新增文件

```text
agentbench/
  cli/features/
    ground_truth.py
  models/
    __init__.py
    structured_client.py
  harness/ground_truth/
    evaluation/
      __init__.py
      contracts.py
      configuration.py
      source.py
      evidence.py
      matcher.py
      service.py
      store.py
      summary.py
      export.py
      assets/
        reproduction.md
        detection.md
        reproduction.schema.json
        detection.schema.json
  sdk/plugin/kuma/
    gt_evidence.py
tests/
  test_gt_evaluation_source.py
  test_gt_evaluation_evidence.py
  test_gt_evaluation_matcher.py
  test_gt_evaluation_store.py
  test_gt_evaluation_summary.py
  test_gt_evaluation_cli.py
  test_structured_model_client.py
  test_kuma_gt_evidence.py
  fixtures/gt_evaluation/
    README.md
    positive/
    near_miss/
    judge_miss/
    incomplete/
```

不提前创建空模块充当实现。按第 12 节顺序，每次创建可被调用、带对应验证的最小闭环。fixtures 使用合成的完整小样本，不复制真实凭证、巨大 trace 或 Agent 源码。

### 1.2 修改已有文件

| 已有文件 | 具体修改 |
| --- | --- |
| `agentbench/cli/features/__init__.py` | 导入新 FEATURE 并加入 FEATURES；不向 cli/main.py 加命令分支 |
| `agentbench/sdk/contracts.py` | 增加可选 SDKGroundTruthEvidenceReader 协议及 SDKReviewEvidence 数据结构 |
| `agentbench/sdk/plugin/kuma/plugin.py` | 实现协议方法，函数内延迟导入 gt_evidence |
| `pyproject.toml` | 将 evaluation/assets 下的 md、json 加入 setuptools.package-data |
| `docs/Ground Truth.md` | 实现完成后添加英文命令、输入输出、LLM 审核标签和限制 |
| `docs/otherLanguages/Ground Truth.zh-CN.md` | 同步中文使用说明 |

首版不修改 suite_runner 的运行主流程、不改变 SDK Judge verdict、不改变现有 GT manifest schema。现有 assessments 校验保留。正式 viewer 接入独立 evaluation 需要后续明确的 API 和页面修改，不声称仅生成 JSON 就已经能在现有页面展示。

## 2 文件职责与内部接口

以下为拟新增签名，数据类字段见后文；实现时保持这个依赖方向：CLI → service → source/evidence/matcher/store/summary，matcher → 通用 model client → ABB provider 配置。

| 文件 | 入口及责任 |
| --- | --- |
| `cli/features/ground_truth.py` | configure_parser、execute、FEATURE；解析 evaluate/show/export 子命令，加载环境，打印结果与退出码 |
| `models/structured_client.py` | StructuredModelClient.generate(messages, schema, request_id) → StructuredReply；只负责模型 HTTP 请求、响应解码、用量、有限重试，不理解 GT |
| `evaluation/contracts.py` | EvaluationConfig、SuiteReviewSource、AttemptEvidence、DefectDecision、EvaluationResult；不导入 CLI 或具体 SDK |
| `evaluation/configuration.py` | resolve_evaluation_config(args, environ)；参数范围、provider/model 优先级、预算和上下文限制 |
| `evaluation/source.py` | load_review_source(suite_dir, registry_path)；读取并冻结 Suite、GT、适用性、Attempt 身份及候选全集 |
| `evaluation/evidence.py` | build_evidence(source, attempt, plugin)；统一证据编号、脱敏、哈希、完整性及引用校验 |
| `evaluation/matcher.py` | assess_attempt(evidence, defects, client, config)；第一阶段复现判断，第二阶段 Judge 匹配，执行 JSON schema 与语义约束 |
| `evaluation/service.py` | evaluate_suite(config, environ, client_factory)；任务队列、预算预留、并发、检查点、异常分类与结果发布 |
| `evaluation/store.py` | EvaluationStore.create/open_resume/save_request/save_response/commit_decisions/finalize；独占锁和原子写入 |
| `evaluation/summary.py` | summarize_evaluation(plan, decisions, task_states)；纯函数，只统计本 evaluation 的固定 Suite |
| `evaluation/export.py` | export_assessments(evaluation_dir, suite_dir)；重新验证引用和当前版本，冲突检测，显式发布兼容 assessments |
| `sdk/plugin/kuma/gt_evidence.py` | read_ground_truth_evidence(directory, case, agent_id) → SDKReviewEvidence；只读 KUMA 本地产物，不调用 judge 或执行容器 |

`evaluation/__init__.py` 仅导出 evaluate_suite 和必要公共数据类型，不在导入时创建目录或读取环境。`models/__init__.py` 只导出通用客户端及异常。

SDKReviewEvidence 定义在 SDK contracts 中，以免 SDK plugin 反向依赖 harness 的评审实现。其字段至少包括 steps、tool_events、file_evidence、report、evidence_refs、capture_state、warnings。通用层将其转换为 AttemptEvidence。

## 3 现有公共能力如何复用

| 已有接口及所在文件 | 使用位置 | 复用限制 |
| --- | --- | --- |
| CommandFeature，`cli/features/base.py`；FEATURES，`features/__init__.py` | CLI 注册 | 沿用 feature registry |
| load_project_environment，`cli/environment.py` | CLI 执行开始 | 只加载用户选择的环境；不保存完整环境 |
| resolve_model_provider、ModelTargetConfig，`runtime/interception/providers.py` | configuration / model client | 解析目标，不是 HTTP 客户端 |
| read_suite、suite_snapshot，`harness/session/__init__.py` | source | 保留 plan/events 身份；不自己根据文件夹名推断 Case |
| reconcile_reports，`observe/result_reconciliation.py` | source | 与 viewer 相同的只读修正路径；使用修正后的快照，记录原始事件哈希与修正结果哈希 |
| registered_units、load_manifest，`harness/ground_truth/manifests.py` | source | 校验 Agent 身份、GT 内容及 observation 哈希；manifest 校验不等于确认其语义为真 |
| within、read_bytes、file_digest，`harness/ground_truth/files.py` | source / evidence | 原有大小限制继续有效；大文件不能无上限加载 |
| digest_json，`harness/session/plan.py` | source / store | 对 JSON 内容计算统一摘要，不把原始文件 SHA 与 JSON 摘要混用 |
| execution_status，`harness/session/attempts.py` | source | 不用业务 status=failed 判断执行无效 |
| discover_sdks、load_sdk，`sdk/discovery.py` | source | 只加载已发现的 SDK，不任意导入用户给的模块路径 |
| prepared_from_json，`harness/session/codec.py` | evidence | 恢复 SDK 需要的 PreparedCase 对象 |
| environment_secrets、redact，`observe/store.py` | evidence / model client / store | 发送前和保存前脱敏；记录脱敏是否影响判断 |
| atomic_json、atomic_bytes，`harness/session/atomic.py` | store | 复用带 fsync 和 Windows replace 重试的写入；调用方先完成脱敏 |
| validate_assessment，`harness/ground_truth/assessments.py` | export | 复用身份、版本、状态约束，不把通过验证当作模型判定正确 |
| filelock.FileLock，现有 pyproject 依赖 | store | 对 GT evaluation 使用独立锁，不长时间占用 Suite writer 锁 |
| jsonschema，现有 pyproject 依赖 | matcher | 本地严格验证，独立于 provider 的 schema 支持 |

不能直接复用的接口：onboarding OpenRouterClient 带 builder 专用 prompt/schema；local Judge relay 带 smoke-test 判断语义和自身配置；Artifacts.save 虽会脱敏，但需要本模块明确控制“脱敏 → 哈希 → 原子写入”，故这里直接组合公共函数。无需为 GT 检测重新实现 Docker、拦截器或模型目录。

benchmark_ground_truth 当前从固定 assessments.json 读入并合并传入 Suites，不能直接用于独立 evaluation 目录。首版 summary 实现纯聚合函数；显式 export 后，现有统计才可消费兼容结果。不要为复用旧汇总而临时替换人工 assessments 文件。

## 4 输入定位与适用性

1. `--suite` 必须指向含 plan.json、events.json 的 canonical Suite。历史散落 JSON 不自动猜测映射。
2. 使用 read_suite → suite_snapshot → reconcile_reports → suite_snapshot 获取一致视图。读取前后检查 plan/events 摘要，变化则有限重读；首版只接受已结束的 Suite，包括已结束但部分失败的 Suite。仍运行或延迟 Judge 未完成时报告 pending，不生成完整 miss 结论。
3. registry 默认使用项目 registry，允许 `--registry` 指定实验 registry。registered_units 当前接收项目根并固定读取 resources/registry.toml：实现中给它增加可选 keyword-only registry_path 参数，默认保持兼容；相对 Agent path 仍相对 registry 所在 resources 的父级解析。对应补充测试，不声称当前签名已支持任意 registry。
4. 通过 registry 定位 GT unit；不直接信任 plan 里的任意绝对路径。实验 unit 必须在显式选定的 registry 中登记。检查 agent_id 和 source_sha256；GT 缺失标记 not_configured，源码不匹配标记 not_applicable，损坏标记 invalid。
5. manifest 中的 criterion 优先提供给模型；expected_behavior 和 observed_behavior 始终提供。可选 model_configuration 等限定条件一并保留，若 GT 声明依赖特定运行条件而本次不满足，记录配置不适用。缺少这些扩展字段不擅自判无效。
6. 枚举全部 Case 和历史 Attempt，包括 SDK 判 pass 的 Attempt。每一对键为 `(suite_id, agent_id, case_index, attempt_id, ground_truth_id)`，不以 case_id 单独去重。
7. 首版可判定的记录要求 execution_status=completed、身份可校验、实际输入输出可读且证据满足相关 GT。执行异常单独记录 execution_error；当前 v1 assessment 禁止这种记录产生布尔结论，首版也遵守。若要覆盖“原生崩溃就是 GT 缺陷”，需后续扩展协议，不能悄悄放宽旧 validator。

适用但因执行异常不可评审的缺陷仍列在本 Suite 目标 GT 中；不会偷偷从目标分母消失。报告单独区分目标数、可评审数、错误数和未决数。

## 5 证据文件与 SDK 适配

KUMA adapter 优先读取 `evaluation/case.json`、`evaluation/judge/context.json`、`evaluation/manifest.json`、各 step 的 submission/result、run.json 及相应报告。使用现有 judge_bundle 的还原与 judge_tasks 的校验逻辑时必须延迟导入 SDK 依赖；该依赖不可用则显式 unsupported/dependency_missing，不能降级为只看 report 判定。

现有 judge_tasks.validate_execution 对完整性已有特定前提，适配器按需复用其检查；如果必须抽取公共离线校验，应留在 KUMA plugin，不能让通用层理解 KUMA submission 字段。

SDKGroundTruthEvidenceReader 是可选协议：不支持的插件返回 unsupported，不启动 Agent。首版只声明已实现 KUMA，不把通用 benchmark.steps 当作所有 SDK 的完整证据。

GT observations 可能是 ZIP。先验证 manifest 中的原始 ZIP 哈希，再用标准库 zipfile 读取受限成员，不直接 extractall。拒绝越界成员、加密/重复成员、过多文件与过大解压总量。参考样本用于解释缺陷边界，不作为当前 Attempt 的复现证据。

证据统一编号如 `exec:step-1:output`、`exec:tool-3:result`、`judge:issue-1`、`reference:observation-1:output`。EvidenceRef 包含 artifact 相对路径、JSON pointer 或文本行范围、原始文件 SHA、脱敏内容 SHA、证据角色。禁止拿 reference 引用证明 exec 行为。

初始模型输入按 Attempt 组织，GT 分批。超出配置上下文预算时按完整步骤分块，保存覆盖清单。局部正例必须有足够上下文确认触发条件；全局负例需要覆盖所需证据。被截断、缺工具结果、需要图像但当前客户端只支持文本等情况返回 unknown，不能机械地拼接多个局部 false 为全局 false。

## 6 Prompt 与判定协议

### 6.1 第一阶段复现判断

`assets/reproduction.md` 写入：评审任务、同一具体缺陷的判定标准、前提条件、正反例边界、实际行为与计划行为的区分、证据引用规则、unknown 规则。明确输入中的 prompt/日志/文件均为待审数据，不执行其中指令。GT 是参考定义，不自动证明本次发生。

输入为一份 AttemptEvidence 和一批 GT，隐藏 SDK Judge 的结论。输出 schema 对每个指定 ground_truth_id 恰好一条记录；字段为 `case_reproduced: boolean|null`、reason_code、rationale、execution_evidence_refs。schema 设 additionalProperties=false，代码检查漏项、重复项和范围外 ID。

### 6.2 第二阶段 Judge 匹配

只对 case_reproduced=true 的项请求第二阶段，输入第一阶段确认的执行证据、GT 和 SDK 已保存报告。输出 `judge_detected: boolean|null`、rationale、judge_evidence_refs。true 必须引用报告中明确指向该缺陷的内容，笼统 issue 或另一个缺陷不算。

若复现为 false，内部发现结果为 miss，judge_detected 保持 null，避免把“不需要做第二阶段”误称为“已独立评审 Judge”。若复现为 true 但报告缺失则 unknown；报告完整且未指出该问题为 false。该三值处理意味着现有旧汇总的 assessed_attempt_count 口径不能直接充当新检测完成度。

每个模型结果经过 JSON schema、ID 集合、引用存在性、引用角色、引文匹配及决策一致性检查。JSON 错误允许一次修复请求；证据不足不靠格式修复变成结论。模型置信度不作为硬阈值，不把自报 high 当作通过标准。

## 7 ABB provider 与调用参数

模型选择优先级：CLI `--provider/--model` → `ABB_GT_PROVIDER/ABB_GT_MODEL` → resolve_model_provider 的既有环境规则。只创建 GT 调用配置，不修改进程中 ABB_MODEL 或 Agent 配置。明确选择的 provider 失败不自动 fallback。

客户端使用 target.base_url、headers、credential_env 和 endpoint_paths；映射没有 chat 能力时拒绝，不发错协议请求。支持现有 OpenAI-compatible chat 请求，不能默认给所有 provider 发送 OpenRouter 的 provider.require_parameters 参数。schema 不受支持时采用 JSON 文本协议加本地严格校验；传输模式属于配置及缓存键。

建议首版默认：concurrency=2、单次 timeout=90 秒、网络重试最多 2 次、结构修复最多 1 次。输入 token 预算和输出上限显式可配置；字符估算只作保守预检，不声称准确 token 计费。context-too-large 触发分块或 unknown，不无限重试。429/指定 5xx/连接错误可退避重试，鉴权错误立即结束。

`--max-requests` 包括第二阶段、网络重试及修复调用。并发派发前集中预留配额，超预算任务保留 pending。记录 provider 返回的 usage，未提供时填 null，不伪造成本。请求重试可能导致服务端已完成但客户端未收到，记录这种不确定性，不承诺恰好一次付费调用。

## 8 运行时目录及文件内容

```text
<suite>/ground_truth/
  assessments.json                 # 现有兼容文件，仅 export 显式写入
  .export.lock
  evaluations/
    gt_eval_<uuid>/
      .writer.lock
      plan.json
      state.json
      summary.json
      assessments.json             # 本 evaluation 的兼容记录副本
      inputs/
        suite-plan.json
        suite-snapshot.json
        ground-truth.json
        evidence-index.json
      evidence/
        <content_sha256>.json
      tasks/
        <task_sha256>/
          task.json
          reproduction.request.001.json
          reproduction.response.001.json
          detection.request.001.json
          detection.response.001.json
          decisions.json
          error.json               # 仅发生错误时产生
      exports/
        <export_id>.json
```

evaluation_id 由宿主生成，禁止模型提供路径。task_id 用规范化身份和配置的摘要生成，不直接把 agent 名当路径。所有输出验证在 evaluation root 内；输入和输出目录不重叠覆盖。

| 文件 | 必须保存的内容 | 写入时间 |
| --- | --- | --- |
| plan.json | schema、evaluation_id、suite_id、输入摘要、SDK版本信息、GT版本、目标矩阵、effective provider/model、prompt/schema摘要、预算、分块策略、创建时间 | 调用模型前，只创建一次 |
| inputs 下文件 | 脱敏且冻结的 Suite/GT 视图；包含完整候选身份，不包含凭证环境 | 规划阶段 |
| evidence-index.json | 原文件摘要、脱敏片段摘要、引用位置、完整性、分块覆盖范围 | 证据准备后 |
| task.json | Attempt 身份、GT批次、输入引用、请求缓存键、待执行阶段 | 请求前 |
| *.request.NNN.json | 实际脱敏 messages、输出schema、模型参数、request_id；不含 Authorization/header秘密 | 每次请求前 |
| *.response.NNN.json | 脱敏响应内容、finish_reason、usage、耗时、HTTP分类及provider request id（如有） | 每次请求后 |
| decisions.json | 完整校验后的逐 GT 结论和依据；失败不留下伪造结论 | task完成时原子写入 |
| state.json | task状态、请求数、重试数、进度、更新时间 | coordinator统一写，worker不并发覆盖 |
| summary.json | 按Agent/GT汇总、命中证据、miss/unknown/not_applicable计数、完成状态 | 检查点与最终发布 |
| assessments.json | 满足现有v1约束的记录；内部unknown诊断不强塞进旧协议 | 生成结果时 |
| exports/*.json | 导出目标、旧文件hash、新文件hash、受影响身份和冲突结果 | 每次显式导出 |

创建顺序为：只读预检 → 获取 evaluation 写锁 → plan/inputs/evidence → task → request → response → decisions → state → summary。每个 JSON 用原子写入；summary 不是唯一事实来源，可从 plan 和已提交 task 结果重建。

## 9 数据结构示例与版本绑定

内部 decisions.json 示例，下面省略的哈希在实际文件中必须是完整摘要：

```json
{
  "schema": "abb.gt_evaluation.decisions.v1",
  "evaluation_id": "gt_eval_example",
  "suite_id": "suite_example",
  "agent_id": "jobsmith",
  "case_index": 0,
  "attempt_id": "attempt_example",
  "input_digest": "<sha256>",
  "decisions": [{
    "ground_truth_id": "cover-letter-invents-cloud-deployment-experience",
    "ground_truth_sha256": "<sha256>",
    "case_reproduced": true,
    "judge_detected": false,
    "outcome": "miss",
    "reason_code": "judge_missed",
    "rationale": "实际求职信新增云部署经历，但完整 Judge 报告只指出另一项问题。",
    "execution_evidence_refs": ["exec:step-1:input", "exec:step-1:output"],
    "judge_evidence_refs": ["judge:report"]
  }]
}
```

兼容 assessment 由程序构造字段：agent_id、case_index、attempt_id、ground_truth_id、ground_truth_sha256、case_sha256、result_sha256、case_reproduced、judge_detected、reviewed_by、reviewed_at、rationale。reviewed_by 使用 `llm:<provider>:<model>:<evaluation_id>`，不能标记成人工。

case_sha256 使用当前生成 Case 的 prepared_case.artifact_sha256，不是 GT 参考 Case 的摘要；result_sha256 对同一 canonical/reconciled snapshot 中的 result 调 digest_json。原始事件摘要、投影视图摘要和原始证据文件 SHA 分开记录。脱敏后的输入摘要只用于本次模型输入重现，不能替换旧协议的来源哈希。

缓存键覆盖 Attempt/GT 身份、原始证据摘要、脱敏输入摘要、GT版本、Case/result摘要、provider/model/endpoint非秘密配置、prompt/schema、客户端协议、分块与判定策略版本。相同配置的 --resume 可复用已提交结果；改变任一关键输入创建新的 evaluation。缓存不跨不同 evaluation 自动共享，避免把不同评审实验混合。

## 10 续跑、导出与统计规则

task状态为 pending → running → completed，或 retryable_error / blocked。进程中断后 running 回到待恢复状态；已有完整且摘要匹配的 decisions 直接恢复，不重复请求。已写 response 但未写 decisions 时优先离线重新校验 response。丢失响应的请求可以重试，但明确记录可能重复调用。

resume 获取同一 evaluation 的锁，并重新校验原始输入摘要；Suite 或 GT 已变化就停止该 evaluation 的续跑，提示新建检测。不能把旧结果静默套用到新源码或新 Judge 报告。长时间模型调用期间不持有原 Suite writer 锁。

export 先读取当前 Suite/GT 并重新调用 validate_assessment。根 assessments.json 中同身份且完全相同记录为幂等跳过；同身份不同结论或元数据为冲突，保留原文件并输出冲突清单，首版不提供 force 覆盖。采用 .export.lock 防止并发导出，并在发布前复查输入哈希；读取中的其他工具始终看到完整旧版或新版。

内部统计以整个 Suite 对每个 GT 取逻辑或，但只允许同一个 Attempt 的复现与识别组成 hit：

| 条件 | GT 状态 |
| --- | --- |
| 任意 Attempt 同时 case_reproduced=true、judge_detected=true | hit |
| 无 hit，全部目标执行及必要评审完成且均有足够证据否定发现 | miss |
| 无 hit，但存在缺失证据、未评审、调用失败、预算耗尽或执行错误 | unknown，附具体原因 |
| GT与源码或必要配置不匹配 | not_applicable |
| 无GT / GT损坏 | not_configured / invalid |

无有效 Attempt 的 Agent 不记 miss。存在 hit 的 GT 即使命中之外还有未知任务，也可确认命中，但 evaluation 完成度仍反映未完成任务。触发覆盖率与 SDK发现覆盖率分别统计；true复现但Judge漏报属于已触发、未发现。

汇总保留 total_target_defects、applicable_defects、hit、miss、unknown、excluded、completed_pairs/expected_pairs。只有所有适用目标已决时给出 final discovery_rate；未完成时 discovery_rate=null，另列 lower_bound=hit/applicable 和 upper_bound=(hit+unknown)/applicable。无适用GT时比率为null。明确这是所选 Suite 的检测结果，不自动声称符合跨SDK固定预算排行榜协议。

## 11 CLI 与用户操作

拟新增接口：

```powershell
agentbench gt evaluate --suite <suite目录> --registry <registry.toml> --dry-run
agentbench gt evaluate --suite <suite目录> --registry <registry.toml> --provider openrouter --model <模型ID> --max-requests 200
agentbench gt evaluate --suite <suite目录> --resume <evaluation_id>
agentbench gt show --suite <suite目录> --evaluation <evaluation_id>
agentbench gt export --suite <suite目录> --evaluation <evaluation_id>
```

dry-run 只读预检，显示 Agent/GT/Attempt 数、不可评审原因和初始调用量范围，不调用 provider、不创建 evaluation。实际 evaluate 输出新目录及每个 Agent 的 hit/miss/unknown。show 只读已有结果。--resume 使用冻结配置，CLI 不允许同时覆盖模型或prompt。

返回码：0=检测已完整完成（即使有 miss），1=检测存在未完成/失败任务或导出冲突，2=输入/配置非法，130=中断且检查点保留。命中率低不作为程序失败。保留可供自动化读取的 summary.json 位置。

Suite 后续自动接入时，在 Suite执行及延迟Judge队列结束后调用同一 evaluate_suite 服务。GT检测有独立状态和退出信息，不回写原Suite pass/fail，不把GT提交给SDK生成器、Agent容器或SDK Judge。

## 12 实施顺序与验收

| 阶段 | 创建或修改内容 | 完成标准 |
| --- | --- | --- |
| 1 输入规划 | contracts/configuration/source、CLI dry-run、registry可选路径支持 | 对现有Suite列出准确目标，能够区分质量失败与执行失败、实验registry与默认registry |
| 2 证据适配 | SDK可选协议、KUMA adapter、evidence、离线fixtures | 输入/输出/工具/文件/报告关联正确；证据缺失不会误判阴性；ZIP边界和引用角色可验证 |
| 3 模型判定 | structured_client、matcher、四个assets、package-data | 使用ABB provider；两阶段prompt独立；结构修复有界；不支持的协议提前失败 |
| 4 持久化与聚合 | store/service/summary、evaluate/show | 崩溃续跑不丢已提交决策；预算不超派发；GT去重和unknown传播正确 |
| 5 兼容导出 | export、gt export、双语使用文档 | v1 validator接受有效记录；人工冲突不覆盖；现有统计可读已导出记录 |
| 6 真实校准 | 冻结小型人工标注集和一次真实provider结果 | 报告pair级混淆情况、unknown和分歧样本，检查成本与重复评审稳定性 |

自动测试的关键样例：同缺陷换措辞；相同关键词但不同缺陷；工具计划未执行；只在参考GT出现的行为；执行正确但Judge误报；执行复现但Judge漏报；pass报告掩盖实际复现；合法提前终止；源码不匹配；Case/证据被修改；同Case多Attempt；跨Attempt不可拼hit；缺报告；分块遗漏；无GT；部分Suite；模型越权引用；provider endpoint/header；429/鉴权/截断响应；Windows并发写入；中断恢复；导出冲突；脱敏影响判据。

实现阶段先跑新增tests，再跑现有 `tests/test_ground_truth.py`、`tests/test_ground_truth_isolation.py`、`tests/test_model_providers.py`、`tests/test_sdk_directory.py` 及受影响KUMA测试。增加 wheel 安装后 assets 可读取检查；`agentbench gt --help` 及子命令帮助必须可在无凭证环境工作。

真实模型验收使用现有保留执行证据，无需为离线评审重新启动容器。若实现改变SDK执行或提交协议，则按仓库要求另补真实容器验收。LLM评审通过格式校验不代表语义准确；正式批量运行前，用冻结标注集检查假阳性、漏判与unknown，不拿待评Suite反复调prompt再当独立评测。

## 13 已有代码依据

- [GT manifest读取](../../agentbench/harness/ground_truth/manifests.py)
- [Assessment校验](../../agentbench/harness/ground_truth/assessments.py)
- [现有GT聚合](../../agentbench/harness/ground_truth/__init__.py)
- [Suite读取](../../agentbench/harness/session/store.py)
- [Viewer的报告修正](../../agentbench/observe/result_reconciliation.py)
- [ABB provider解析](../../agentbench/runtime/interception/providers.py)
- [Provider目录配置](../../agentbench/runtime/interception/model-providers.toml)
- [KUMA持久化Judge上下文](../../agentbench/sdk/plugin/kuma/judge_bundle.py)
- [KUMA离线执行证据检查](../../agentbench/sdk/plugin/kuma/judge_tasks.py)
- [持久化原子写入](../../agentbench/harness/session/atomic.py)
- [GT现有使用约定](Ground%20Truth.zh-CN.md)
