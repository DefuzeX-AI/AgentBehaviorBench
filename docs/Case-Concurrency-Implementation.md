# ABB Case 并发实施说明

本文描述当前 Case 并发接口及改动范围。配置和任务语义见 [Case 并发设计](Case-Concurrency-Design.md)。本轮已完成同一 Agent 多 Case 的真实 Docker、目录 SDK 与 PyPI KUMA 验收，证据列于文末。

## 使用

```dotenv
ABB_MAX_PARALLEL_CASES=4
```

```bash
agentbench run --no-view --output results/benchmark.json
```

一个 Agent 请求 4 个 Case 时，实际线程上限也是 4。多个 Agent 共享上限，计算方式为 `min(配置值, 所选 Agent 的 Case 总数)`。日志中 `configured_workers`、`effective_workers`、`total_case_count` 可用于核对。Agent 的 Case 集合准备与 Case 执行共享唯一线程池和同一在途上限；每个 Agent 只准备一次。镜像按构建目标复用，每个实际执行的 Case 使用独立容器、网络和产物目录，线程数不等于镜像数。

本地 `.env` 的原 Agent 并发键已迁移到 `ABB_MAX_PARALLEL_CASES`，保留原数值；代码不接受旧键或旧字段作为别名。`.env.example` 默认值为 `1`。

## 文件与职责

| 文件 | 当前职责 |
| --- | --- |
| `.env.example` | 唯一 Case 并发变量与默认值 |
| `agentbench/harness/concurrency.py` | Case 线程配置验证、环境读取和实际线程数量计算 |
| `agentbench/cli/environment.py` | 加载 `.env` 后冻结环境与并发设置 |
| `agentbench/cli/configuration.py` | CLI 参数和注入依赖 |
| `agentbench/cli/features/run.py` | 默认评测入口，向执行层传递快照 |
| `agentbench/cli/features/certify.py` | 单 Agent 认证，也按 Case 总数应用并发设置 |
| `agentbench/cli/features/evaluate.py` | 评测入口复用同一配置与执行逻辑 |
| `agentbench/cli/trace_runtime.py` | SDK factory、Trace sink 与 Case 配置的连接 |
| `agentbench/harness/runner/suite_runner.py` | 校验 SDK 能力、准备 Agent、构造 Case 任务并返回有序聚合 |
| `agentbench/harness/jobs.py` | 准备与 Case 工作任务、Case 身份、Input 回调与终态 |
| `agentbench/harness/scheduler.py` | 准备与 Case 共用线程池和在途预算、补位、完成收集、取消及部分结果 |
| `agentbench/harness/events.py` | 协调线程事件队列、tick 与保留任务身份的有界 Trace 预览 |
| `agentbench/harness/progress.py` | agent_job_id、job_id、case_index、case_id 和阶段元数据 |
| `agentbench/harness/result.py` | CaseResult、EvaluationFailure 及其派生 Agent 汇总 |
| `agentbench/sdk/contracts.py` | SDK Case 并发能力和执行上下文 |
| `agentbench/sdk/runtime.py` | 共享 Suite 服务与独立 Case runner 创建 |
| `agentbench/sdk/plugin/kuma/benchmark.py` | 准备一次 Case 集合，绑定独立 Case 执行器 |
| `agentbench/sdk/plugin/kuma/service.py` | 独立 Case 目录、运行容器、证据写入及身份传播 |
| `agentbench/runtime/services.py` | Suite 生命周期的构建和 Docker 服务 |
| `agentbench/runtime/docker/build_coordinator.py` | 构建限流、相同目标去重和取消 |
| `agentbench/runtime/contracts/execution.py` | 取消信号、运行预算和基础设施错误 |
| `agentbench/cli/execution.py` | 实际 Case 数量显示、事件连接、错误保留、部分结果恢复、Viewer 生命周期 |
| `agentbench/cli/result_export.py` | Case 和 Agent 结果序列化、200 ms progress 批量写入、立即刷新的生命周期、恢复去重 |
| `agentbench/cli/terminal_ui/progress.py` | 独立 Case 前缀与并发进度输出 |
| `agentbench/cli/terminal_ui/llm_activity.py` | Case/Run/Call 身份的追加式 LLM 输出 |
| `agentbench/cli/viewer.py` | 从事件重建 Agent 聚合、Case 结果和每 Case 步骤 |
| `agentbench/observe/view_api.py` | Agent/Case 状态投影与真实证据目录索引 |
| `web/src/App.jsx` | Case 并发数、总量、队列统计与 Agent 筛选 |
| `web/src/RunSidebar.jsx` | 同 Agent 多个 Case 状态及各自的证据入口 |
| `web/src/trace.js` | 时间线中的 Case/Run/Job 身份 |

## 接口收敛

SDK 的当前执行契约是 `prepare_cases` / `run_case`，使用不可变 Case 描述与独立执行器。原 Agent 粒度调度路径、旧 SDK 执行入口和协议兼容模块已删除，包括 `agentbench/sdk/defuzex.py` 及 `agentbench/harness/protocols/` 下的 `__init__.py`、`evaluation.py`、`sdk.py`。SDK 由目录插件发现机制选择，不通过硬编码的备用 SDK 选择路径。

CLI 直接使用标准 `SuiteRunner.run(on_event=..., on_tick=...)`；已删除签名探测、能力反射和旧 runner 回调落盘分支。`on_event` 是执行事件的唯一落盘通道，`on_progress` 与 Agent 回调只负责显示。旧日志缺字段时的读取防御保留，但不构成另一条运行路径。旧 Agent 并发设计文档已由本文及 Case 设计文档替代。

## 日志读取契约

`run_started` 保存 `selected_agent_ids` 和 `selected_case_counts`，因此准备阶段即可显示所有 Case 的排队状态。`case_completed.case_result` 包含该 Case 的终态、独立 benchmark 或错误；`agent_completed.item.case_results` 包含按索引排序的全部 Case 结果。

Viewer 的 `jobs` 是 Agent 聚合数组，每项有 `cases` 和 `counts`，不在 Agent 顶层存储一个会被并发覆盖的当前 Case。`agents[].case_results` 可在 Agent 尚未全部完成时由 Case 事件重建。`agents[].cases[].step_events` 保留同一 Case 的完整步骤。

Suite JSON 由协调线程写入，普通 progress 在并发模式下按 200 ms 或 256 条事件阈值批量刷新；`on_tick` 负责空闲检查，生命周期与终态立即刷新。Case 原始产物与完整 Trace 由各任务在独立目录落盘。

对外结果 JSON 仍然是事件数组。内部 Case 索引为 0，终端和页面显示从 1 开始。证据 API 只返回已经存在并验证通过的目录；Case 排队记录没有伪造的 Run ID。

## 回归与真实验收

本轮最终 Python 全量结果为 **161 passed, 6 skipped**（1.26 s）。Web **20 passed**，生产构建成功。全量测试中的可选真实环境测试另行显式启用，结果见下表。

从仓库根目录执行：

```bash
.venv/bin/python -m pytest -q
```

Web 验证在 `web/` 目录执行：

```bash
npm test
npm run build
```

回归覆盖准备和执行共用 P 个槽位、同 Agent 多 Case、补位、乱序结果排序、Case 身份隔离、部分失败、取消、日志刷新与终端异常。最后补充的异常路径覆盖 `on_tick` 抛出取消异常时的退出，以及 Case 排队事件写入失败时保留全部已准备 Case 的身份。

### 真实 Docker：4 项通过

本轮正常场景均为 **1 Agent × 2 Case，P=2**；取消场景为 **1 Agent × 3 Case，P=2**。每项都记录 `prepare_count=1`，取消时第三个 Case 未派发。镜像构建、容器检查与资源清理均使用真实 Docker。

| 场景 | 实际观察 | 可追溯证据 |
| --- | --- | --- |
| 两个 Case 并行执行 | 同时 2 个执行容器，2 个 Case succeeded；两容器复用同一镜像 | [acceptance.json](../results/verification/docker-cases-run-61cca4de2f87401caa3ababdec2271a0/acceptance.json) |
| 两个运行中 Case 取消 | 同时 2 个执行容器，2 cancelled + 1 skipped | [acceptance.json](../results/verification/docker-cases-cancel-ff0d2963b19a4b4db6e0299331e074c6/acceptance.json) |
| 两个 Case，各配独立 interceptor | 同时 4 个容器：2 个执行容器 + 2 个 interceptor；两 Case succeeded，本地上游收到两个独立 Case 标记 | [acceptance.json](../results/verification/docker-cases-paired-run-4219742a27ad4facad51900f35ac090c/acceptance.json) |
| 两个配对容器组取消 | 同时 4 个容器，2 cancelled + 1 skipped | [acceptance.json](../results/verification/docker-cases-paired-cancel-ac57631a4db444d1a7c479525a82c953/acceptance.json) |

四份记录的 `controller_errors`、`remaining_containers`、`remaining_networks` 都为空。配对场景中，两 Case 复用同一执行镜像与同一 interceptor 镜像，但各自绑定不同 interceptor 容器及网络；`case-marker-0/` 与 `case-marker-1/` 各自保留 `network.jsonl` 和 `run.json`。这直接验证镜像复用与容器隔离可以同时成立。

Docker 验收命令：

```bash
DOCKER_CONTEXT=default \
ABB_DOCKER_CASE_BASE_IMAGE=abb-concurrency-acceptance-base:local \
.venv/bin/python -m pytest tests/test_docker_acceptance.py -q -s
```

本轮真实容器证据的并行规模是 2 个 Case；N=4 的配置示例与线程上限规则不代表本轮执行过 4 个 Case 的真实容器验收。

### 目录 SDK：1 项通过

实际执行命令：

```bash
DOCKER_CONTEXT=default \
ABB_SDK_DOCKER_IMAGE=defuzex-agentbench/kuma-pypi-acceptance:aca7be350b53696e7270c7a9f9baf89350e52f38158ca611b5928c2f05aee466 \
.venv/bin/python -m pytest tests/test_sdk_directory.py::test_directory_adapter_retains_real_container_run -q -s
```

[Suite 事件日志](../results/verification/sdk-directory-ccb12d15d75a4f9c982b19cee52dcedc/suite-20260914-041905.json) 记录 1 个 Agent、2 个 Case、`configured_workers=1`、`effective_workers=1`，两 Case 均 succeeded，各自有独立 job_id 和 run_id。产物中的 `case-0000/`、`case-0001/` 分别包含 Case、Agent output、Judge、Run 和容器日志，Judge 均通过。此项验证目录 SDK 契约与每 Case 产物完整性，采用顺序执行。

### PyPI KUMA：1 项通过

PyPI 验收命令：

```bash
DOCKER_CONTEXT=default \
ABB_KUMA_PYPI_BASE_IMAGE=abb-concurrency-acceptance-base:local \
.venv/bin/python -m pytest tests/test_kuma_pypi.py::test_real_pypi_overlay_and_offline_case_judge -q -s
```

[verification.json](../results/verification/kuma-pypi-3b38645000b24a978bba82ef80007eb6/verification.json) 记录从 PyPI 安装的 `kuma-defuzex==0.2.4`、当前源码运行层 `/opt/abb-current-runtime`、目录插件适配器及 `prepare_cases` / `run_case` 契约；状态为 passed。对应 [Judge](../results/verification/kuma-pypi-3b38645000b24a978bba82ef80007eb6/judge.json) 与 [Run](../results/verification/kuma-pypi-3b38645000b24a978bba82ef80007eb6/run.json) 保留真实容器执行结果。

目录 SDK 与 PyPI 验收使用 `offline-custom` Case/Judge provider 和 `network=none`；PyPI 安装来源为 `https://pypi.org/simple`。这些证据验证安装、源码覆盖、SDK 契约和离线容器执行，未调用线上 KUMA 业务服务或付费 LLM。上面的 `ABB_DOCKER_CASE_BASE_IMAGE`、`ABB_SDK_DOCKER_IMAGE`、`ABB_KUMA_PYPI_BASE_IMAGE` 仅是测试环境的显式验收开关，不是产品并发配置；用户仍只填写 `ABB_MAX_PARALLEL_CASES`。
