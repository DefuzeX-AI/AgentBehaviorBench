# ABB Case 并发设计

## 1. 配置和执行单位

唯一业务并发配置：

```dotenv
ABB_MAX_PARALLEL_CASES=4
```

Case 执行任务的单位是一个 Case。同一个 Agent 的多个 Case 可以同时执行；多个 Agent 共享同一个 Case 线程池。一个 Case 内的 Input、Agent 调用和提交顺序保持不变。

设配置为 N，所选 Agent 请求的 Case 数为 C₁…Cₐ：

```text
T = sum(C₁…Cₐ)
P = min(N, T)
ThreadPoolExecutor(max_workers=P)
```

| 选择 | 配置 N | 实际线程上限 P |
| --- | ---: | ---: |
| 1 个 Agent，4 个 Case | 4 | 4 |
| 1 个 Agent，10 个 Case | 4 | 4 |
| 2 个 Agent，各 3 个 Case | 4 | 4 |
| 3 个 Agent，各 1 个 Case | 4 | 3 |
| 任意 Agent，共 8 个 Case | 1 | 1 |

默认值为 `1`。配置必须是正整数，空值、零、负数、浮点数和布尔值均报配置错误。CLI 先加载 `.env`，已有进程环境值优先，再冻结环境快照。库调用使用显式 `ConcurrencySettings(max_parallel_cases=N)`。

启动输出：

```text
Case workers: 4 (configured: 4)
```

这里的线程数限制 Agent 的 Case 集合准备和 Case 执行工作，不计入 Viewer、Docker 日志读取或终端刷新等辅助线程。

准备任务与 Case 执行任务共享这个线程池及 P 个在途任务预算。准备时会占用工作槽位，不会额外开出一组准备线程。配置为 1 时也使用同一工作线程／协调线程事件流程。

## 2. 线程、镜像、容器的数量关系

Case 数量决定工作任务数量；镜像用于复用运行环境；容器承载某一次独立执行。

| 项目 | 规则 |
| --- | --- |
| Case 工作线程 | 最多 P 个，完成一个后补充一个 |
| 同时执行的 Case | 最多 P 个，包括同一 Agent 的 Case |
| 一个 Case 的评测容器组 | 1 个执行容器 + 1 个 interceptor 容器 |
| Case 执行阶段容器总数 | 最多 2P 个评测容器，不包括 Docker/BuildKit 内部辅助容器 |
| 镜像总数 | 与不同镜像目标和缓存有关，不等于 Case 数或工作线程数 |
| 镜像构建 | 程序内部协调，相同构建目标去重并限流，无第二个用户配置 |
| Case 生成准备阶段 | 每个 Agent 的 Case 集合准备一次，准备容器和执行容器分别管理 |

例如一个 Agent 有 10 个 Case、N=4：产生 10 个 Case 任务，最多 4 个同时执行；这些 Case 复用镜像，但使用独立容器、网络和证据目录。Case 生成不是把每个 Case 再生成一遍。

## 3. 调用链与任务归属

```text
CLI .env -> ExecutionEnvironment 快照 -> ConcurrencySettings
    -> SuiteRunner
       -> 准备任务与 Case 任务队列，共享 P 个在途任务预算
       -> 唯一 ThreadPoolExecutor(P)
          -> PreparationJob: 每个 Agent 准备一次 Case 集合
          -> CaseJob 0: 独立 runner / runtime session / artifact directory
          -> CaseJob 1: 独立 runner / runtime session / artifact directory
          -> ...（准备完成后才派发该 Agent 的 Case）
       -> 协调线程消费事件、刷新日志、合并 Case 结果
       -> 按注册顺序返回 Agent 聚合结果
```

Agent 父任务负责准备和汇总。SDK 使用 `prepare_cases` 生成不可变 Case 描述，再通过独立 runner 的 `run_case` 执行一个 Case，不共享可变 Case 游标。SDK 必须声明所需能力并支持取消，缺少能力时在派发前报配置错误。配置为 1 也执行这一协议，不保留另一条串行 Agent 运行路径。

每个 Case 有独立 `job_id`；父 Agent 的标识放在 `agent_job_id`。`case_index` 从 0 开始，用户界面显示 `case_index + 1`。生成进度属于父 Agent，`phase=generate`，没有执行中的 Case 索引；Case 执行进度使用 `phase=execute`。

## 4. 事件协议

| 事件 | 身份与用途 |
| --- | --- |
| `run_started` | suite、Agent 选择、每个 Agent 的请求 Case 数、总 Case 数、配置和实际线程数 |
| `agent_queued` / `agent_started` | 父 Agent 的稳定 job_id；排队和准备状态 |
| `case_queued` | 独立 Case job_id、agent_job_id、case_index、case_id |
| `case_started` | Case 实际开始执行 |
| `progress` | 当前 Case 的阶段；生成阶段使用父 Agent 身份 |
| `step_started/completed/failed` | 完整 Case 身份与 Input 身份 |
| `case_completed` | `case_result`，保存该 Case 的终态和结果 |
| `agent_completed` | `item`，包含有序 case_results；全部 Case 终态或准备失败后发出 |
| `suite_completed` / `suite_failed` | 最终汇总或原始执行错误 |

Suite JSON 的事件写入与终端呈现回调在协调线程执行；Case 原始产物和完整 Trace 由各工作任务写入各自独立目录。CLI 只通过 `on_event` 保存执行事件，展示回调不重复落盘。并发模式下，普通 progress 采用 200 ms 刷新阈值；协调线程通过 `on_tick` 在没有新事件时也检查刷新，无额外定时写入线程。缓冲达到 256 条提前写入，事件不会被丢弃。Case/Agent/Step 生命周期、成功失败阶段、退出和错误立即写入；单线程模式立即写入 progress。

结果文件保持 JSON 事件数组，通过临时文件和原子替换发布完整快照。LLM 大型原始证据写入独立 Trace 文件；有界 UI 预览必须保留 Case/Run/Call 身份。结果脱敏复用启动时的环境快照。

## 5. 结果模型

```text
BenchmarkSuiteResult
  items[]                     # Agent 注册顺序
    SuiteAgentResult
      agent_id
      requested_case_count
      preparation_error?
      case_results[]          # case_index 顺序
        CaseResult
          agent_id, case_index, job_id, case_id
          status              # succeeded/failed/cancelled/skipped
          benchmark?          # 仅该 Case 的已完成评测
          error_type?, error_message?
```

`benchmarks`、完成/尝试/跳过数量、Agent 总状态和错误信息均从 Case 结果及准备错误派生。不能用一个“最后一次 benchmark”代替整个 Agent 的 Case 集合。

Case 执行失败只标记对应 Case；其他 Case 的输出和 Judge 必须保留。输入失败、Judge 不通过、取消和未派发的 skipped 分开保存。返回和页面按 Agent 注册顺序再按 Case 索引排列，与实际结束顺序无关。

## 6. 终端与 Viewer

并发模式采用永久追加的身份前缀，避免同一 Agent 的多个 Case 争用一个动画面板：

```text
[agent-a | case=1 | job=case-job-1] case_started: running
[agent-a | case=2 | job=case-job-2] case_started: running
[agent-a | case=2 | job=case-job-2] case_completed: succeeded
```

左侧展示 Agent 聚合及其每个 Case 的独立状态。一个 Agent 可以同时有多个 running Case；生成状态单独显示。未创建证据目录的 Case 只有队列状态，不能伪造可点击的 Run。真实 Run 经所属 Agent、run.json schema、运行 ID 与目录边界验证后才可访问。

Suite 页面显示 Case 总数、线程上限、排队和运行数量。步骤按 Case 分组，Agent 筛选不会把同一个 input_id 的不同 Case 合并。

## 7. 失败、取消和清理

工作线程定期检查取消信号，Docker 构建、准备、执行和清理使用有限超时。取消 Future 不能停止正在运行的线程，必须通过运行控制和资源回收完成退出。协调线程停止新派发，同时继续消费在途事件。

取消时保存已完成 Case；未完成任务记录 cancelled 或 skipped，并补存异常携带的 partial_items。补存按 Agent 和 Case 索引去重。终端输出、结果写入和 Viewer 清理的次生异常不得覆盖原始运行错误。写盘失败时保留待写事件，并明确报告部分结果未能保存。

## 8. 验收边界

本轮全量 Python 回归为 `161 passed, 6 skipped`，Web 为 `20 passed` 且构建成功。真实 Docker 验收使用 **1 个 Agent、2 个并行 Case、P=2**：准备只执行一次，普通执行观测到 2 个容器，配对 interceptor 执行观测到 4 个容器；同类镜像复用，各 Case 容器和网络独立。取消场景请求 3 个 Case，得到 2 个 cancelled 和 1 个 skipped，4 项 Docker 验收均无残留容器或网络。

目录 SDK 和 PyPI KUMA 各完成 1 项真实容器验收。目录 SDK 的 2 个 Case 使用 P=1，验证目录适配和每 Case 产物完整性；并行重叠的证据来自上述 Docker 测试。表中的 N=4 是配置与调度规则示例，本轮真实容器验收规模为 2 个并行 Case。具体命令、产物路径和 SDK 验收范围见 [实施说明](Case-Concurrency-Implementation.md#回归与真实验收)。
