# ABB 十项缺陷修复计划

日期：2026-09-10。对应 [ABB-ISSUES-REPORT.md](ABB-ISSUES-REPORT.md) 的 #1–#10。

本计划已执行。逐项实现与实际验收结果见 [ABB-ISSUES-FIX-RESULTS.md](ABB-ISSUES-FIX-RESULTS.md)。下文保留原设计和验收目标；原生 Linux 实机与完整真实付费评测未在本机执行，不能据离线通过声称这些环境已认证。

## 1. 基线、目标与约束

当前仓库 HEAD 为 `e87bf3e`，与报告记录一致，但工作区不干净：存在 `agentbench/cli/main.py` 的已有修改，以及 `resources/agents/02-deer-flow/` 的已有删除。实施时保留这些变更，不 reset、不恢复删除、不混入修复提交。

目标：修复十项实际契约缺陷，使原版 Agent 能通过现有接口正确执行、被观测和归档。上游 `agent/` 源码、业务提示词、工具返回值均不改；不得通过替换搜索、模型客户端或数据库来掩盖问题。

### 保持的架构

| 所属层 | 继续负责 | 不应承担 |
| --- | --- | --- |
| CLI / composition root | 参数、路径、插件选择、展示、统一结果文件 | 按 Agent 名称分支，手写第二套 SDK handshake |
| SuiteRunner / EvaluationRunner | Case 调度、Input/Submission 顺序、结果汇总 | KUMA 私有目录解析、LangGraph Context 实例化 |
| RuntimeFactory / DockerRuntime | 运行环境、构建、隔离、进程和文件生命周期 | 公司研究逻辑、Judge 判定 |
| LangGraphAdapter | 图加载、调用协议、Context、输入输出适配 | 模型名称映射、评测策略选择 |
| Observe | 活体事件、OTel 导出、关联、证据可用性 | 补造历史 span、以时间接近猜父子关系 |
| Evaluation SDK plugin | SDK 私有选项、Case/Judge 接口和私有产物 | 决定 ABB 是否保存标准 BenchmarkResult |
| Registry | Agent 身份、位置、启用状态、就绪状态 | 下载依赖、读取真实密钥、执行 Agent |

“没有硬编码”指不绑定某个 Agent、模型、宿主路径、供应商实现或测试结果；不意味着消灭协议常量。JSON schema 名称、合法状态集合、HTTP header、容器内部路径等可以是集中声明并有测试的契约常量。不得将这些常量伪装成任意可执行配置语言。

### 对报告建议的校正

- #1 的 `chmod(0777)` 有复现价值，但最终方案优先消除“容器必须向宿主目录写私钥”的依赖，而不是放宽目录权限。
- #2 不能机械地在每个 Input 中执行 `asyncio.run()`；一个 SDK Run 的异步资源应共享同一事件循环，且在循环关闭前完成清理。
- #3 是报告所测客户端版本的覆盖缺口；不能推广为所有 OpenAI SDK 都用 `httpx2`。必须按实际传输类测试。
- #4 `{}` 与“未提供 Context”不同。不能用 `if context` 丢掉显式空映射，也不能把任何声明 `context_schema` 的图都判定为缺配置。
- #6 当前 `evaluate --output` 的 help 明确写的是 SDK output 别名。方案保留兼容性，另外提供 ABB 标准结果的参数，避免同一个路径被当文件和目录使用。
- #8 当前 `docs/CLI.md` 已提到前端构建，因此“完全没有文档”已不准确；仍缺启动预检、统一提示及明确的部署说明。
- #9 `ready` 表示可执行接入，不表示 Judge 通过。旧文档、测试和注册值冲突需要修复，但不能仅因 Judge issue 就把 Agent 降级。当前工作区已删除 Deer Flow，不安排恢复或重新接入它。
- #10 实际 runtime 缺省值是 `in_process`；Dockerfile 相对 `build.context` 解析。报告示例中的默认 docker 和直接拼 `agent_path / dockerfile` 都不应照搬。

## 2. 实施顺序与提交边界

每个编号独立交付修复及其回归测试，下面的批次表示依赖顺序，不要求开启并行 Agent。

| 批次 | 问题 | 目标 / 依赖 |
| --- | --- | --- |
| A | #1、#10、#5 | 消除 Linux 启动和外部工作区接入障碍；三项可独立提交 |
| B | #2 → #4 | 统一调用生命周期，再增加 Context；#4 本身可独立开发，联合验收需 #2 |
| C | #3 | 补齐真实客户端的关联能力；Docker 联合验收依赖 #1 |
| D | #6 → #7 | 先使标准结果始终保存，再接入 host 证据；#7 同时依赖 #2 |
| E | #8、#9 | Viewer 交付体验和状态一致性；#9 的语义测试可先做，最终状态以证据核对为准 |

每项实施前先把报告复现转成“正确行为应通过”的回归测试。注意：原报告脚本 **exit 0 表示缺陷仍存在**，不能把它直接当修复通过信号；其非零也可能是环境错误，必须检查断言和具体失败原因。

## 3. #1 — 原生 Linux Docker 无法创建 CA

**优先级：P1。代码落点：** `runtime/docker/runtime.py`、`runtime/docker/interceptor_policy.py`，必要时仅调整 interceptor entrypoint 的 CA 初始化。对外继续返回 `RunningModelInterceptor.ca_certificate`，不改 Agent trust 接口。

### 修复步骤

1. 用非 root 宿主用户、native Linux Docker 和当前 capability policy 复现“新文件创建失败”；不是对已存在文件做 touch。
2. 移除 `/run/defuzex/ca` 的宿主可写 bind mount。CA store 在 interceptor 自己的 `/run/defuzex` tmpfs 内创建，私钥始终留在该容器内。确认 CA 子目录在启动时存在、归容器进程所有。
3. 将当前 `_wait_for_interceptor()` 拆成两个顺序条件：先等 interceptor ready，再通过现有 Docker 命令封装导出 **单个公有证书文件** 到宿主临时文件。可用 `docker cp container:固定证书路径 临时文件`，不复制目录、不导出私钥、不使用容器 shell 拼接。
4. 宿主读取并校验证书为非空 PEM 公钥证书、无 PRIVATE KEY 块，再由宿主进程写入它自己创建的最终文件并原子替换。设置 Agent 可读的公有证书权限；密钥文件继续在私有临时父目录内，不依赖 Docker cp 的文件所有者语义。
5. 原有 trust 插件继续只读挂载该公有证书。将 secret directory 创建、密钥解析、启动、导出都纳入同一失败清理范围，防止现有 try 之前的异常留下临时文件。
6. 失败时保留经脱敏的启动诊断，删除 interceptor、临时证书和本次网络。不得添加 `privileged`、`CAP_DAC_OVERRIDE` 或固定宿主 UID。

### 验收

- 离线命令测试：无 CA 可写 bind mount；只复制证书文件；Agent 挂载只读公有证书；私钥从未进入宿主结果目录。
- native Linux、宿主 UID 非 0、umask 分别为 022/077：真实 interceptor 能生成 CA、导出证书并启动最小受控 TLS 请求。
- Docker Desktop 运行同一验收；rootless 不凭空宣称支持，如进入支持矩阵必须单独验证其 netfilter 能力。
- 注入生成失败、导出失败、损坏证书、超时、取消：无残留运行容器/网络/secret directory；不得启动缺少有效 CA 的 Agent。
- 复用 `tests/test_docker_runtime.py`、`tests/observe/test_interceptor_image.py`；增加显式 opt-in native Linux Docker 验收。mock 命令成功不能替代 Linux 真实验收。

**架构与无硬编码说明：** 修复 Docker 与 CA 文件的所有权边界，适用于所有声明拦截的 Agent；CA 内部路径属于 interceptor 契约，集中定义，不按 OS 名称、用户名或 Agent ID 特判。相比 chmod，此方案增加少量公有证书导出逻辑，但减少宿主与容器的权限耦合。

## 4. #2 — Host 执行只调用同步 invoke

**优先级：P1。代码落点：** `harness/runner/benchmark_runner.py`、必要的 `running_agent.py` 生命周期接口、现有 adapter 异步接口。

### 修复步骤

1. 使用真实最小 StateGraph、一个 async 节点和本地 SDK，复现 host 的完整 get_input → invoke → submit 链，不只直接测 adapter。
2. 将 host runner 的执行核心变为一个协程：启动/加载 Agent、创建 SDK Run、循环 Inputs、提交、关闭资源都在一个生命周期内完成；每一步 `await running.ainvoke(...)`。
3. 保留现有同步 `run()` 及 EvaluationRunner 协议，用一个同步入口驱动整个 Run 的协程；禁止每个 Input 新开循环。支持 Python 3.10，不能无条件使用仅 3.11 存在的 `asyncio.Runner`。
4. 为直接异步调用提供明确的 `BenchmarkRunner.arun()`；同步入口检测调用线程已经有运行中的 loop 时，给出使用 arun 的错误提示，不使用 nest_asyncio，也不暗中换线程执行整个 Agent。SuiteRunner 和既有第三方同步 runner 协议不强制改成 async。
5. 对只有同步调用的图，继续复用 `LangGraphAdapter.ainvoke()` 中现有 `asyncio.to_thread` 兼容路径，不在 harness 再建图类型分支。
6. 保留提交顺序、一次性提交、稳定 thread_id、回调时机。失败信息保存原始异常类型和脱敏原因；不得只留下 `AgentInvocationError` 外壳，也不得将包含密钥的完整异常直接拼到所有结果中。
7. async close 若存在必须在同一循环 await；普通 close 继续调用。取消不重复 submit、不把未完成 Input 写成成功；对阻塞同步线程，不声称可以强制终止它，按现有 runtime 清理能力处理。

### 验收

- 一个 SDK Run 连续三个 Input，async Agent 三次完成并正确提交，节点记录到同一个 loop；复用 loop-bound 对象仍然可用。
- sync-only 图、混合 sync/async 图、已有 Company binding、容器执行分别回归。
- `run(registration, sdk_run=...)`、注入 plain SDK、兼容 run_defuzex 三个入口都覆盖，避免只修其中一个分支。
- 第二步异常时保留第一步结果，失败回调一次、失败提交最多一次、关闭一次；Judge 异常不重发 Agent 输入。
- active-loop 调用 arun 正常；active-loop 误用同步 run 提示明确且无未 await coroutine 警告；两次独立 Run 不串资源。
- 扩展 `tests/test_benchmark_runner.py`、`tests/test_sdk_injection.py`、`tests/test_langgraph_adapter.py`。

**架构与无硬编码说明：** 使用所有 Adapter 已有的异步端口，不识别 react-agent、Company 或节点名称。同步 SDK handshake 保持现有契约，不借机改造 SDK 协议或复制评测循环。

## 5. #3 — httpx2 / aiohttp 请求没有框架 span 关联

**优先级：P1。代码落点：** `observe/correlation.py`、现有 Observe 摘要/API/UI，interceptor 侧只复用现有 header 消费和移除规则。

### 修复步骤

1. 建立真实客户端到 loopback 服务的矩阵：`httpx`、`httpx2` 的 sync/async，`requests`、`aiohttp`，以及真实 OpenAI/LangChain 和 Tavily 调用路径。记录实际装载模块和版本，避免根据 SDK 名称猜传输。
2. 在 Observe 内将“从当前上下文取 span、检查目标、生成关联 header”与“客户端 hook 的安装/恢复”分开。用小型可注册 hook 集合承载各传输适配，沿用本项目 Observer 注册风格；不新增自动扫描依赖的庞大插件系统。
3. httpx/httpx2 可共享实现，但以实际类对象去重，避免未来别名导致双重 patch；包装函数必须捕获各自 original，避免循环闭包晚绑定。
4. aiohttp 单独处理 URL/base_url、headers 和重定向；保留重复 header 和原有认证/请求参数，不能简单 dict 化多值 header。以测试锁定所用库版本；依赖缺失是 unavailable，不吞掉其他安装错误。
5. 关联只在隔离 worker 的有效 scope 生效。安装幂等、嵌套引用计数与锁保护全局 patch；当前 span/允许目标由 ContextVar 决定，不让并发 Run 共享错误闭包。退出及异常后恢复原函数。
6. 目标来自 manifest 的模型/工具路由；每个实际跳转目标重新判定。跨域 redirect 不能把关联 header 带到未声明站点；复用 Request 时不能留下上一次 span。interceptor 转发前移除内部 header。
7. 在结果中统计有效链接、未链接和未知 span 引用，按真实框架 span 校验关联。未链接仍保存原始记录并标注原因；“不支持此传输/未捕获当前 span/未知原因”分开，不按时间猜链接。

### 验收

- 真实 OpenAI 客户端请求和真实 Tavily 请求分别携带当前 LLM/tool span；一个外层请求不误链接到相邻节点。
- 并发两条节点链、重试、流式、sync/async、异常退出、嵌套 scope、复用客户端及 Request 均不串 span。
- 未声明域名、相对 URL、base_url、跨域跳转、重复 header 有专项用例；受控上游确认最终收不到 `x-abb-framework-span`。
- 移除任一可选依赖，其余客户端仍工作；未知客户端如实报告未关联；原生 Gemini gRPC 保留已知“不支持精确框架关联”的边界。
- 不仅测试 header：核对 framework 与 network 的 request/response call_id 和 span_id，不能只有字段非空就判成功。
- 新增 `tests/observe/test_correlation.py`，回归 `tests/observe/test_interactions.py`、`tests/interception/test_addon.py` 和受控 Docker 链路。

**架构与无硬编码说明：** 客户端协议适配有明确注册点，扩展新传输不改 Agent 或 harness；域名来自配置，模型版本来自实际调用。只添加观测 metadata，不改模型/工具语义。支持库列表是公开的能力矩阵，不伪装“任意 SDK 自动兼容”。

## 6. #4 — LangGraph Runtime[Context] 没有传递通道

**优先级：P1。代码落点：** `adapter/langgraph/config.py`、`adapter/langgraph/adapter.py`、相关配置文档和测试。

### 修复步骤

1. 给外层 manifest 增加可选 `[adapter.context]`，值为可跨进程表示的普通数据映射；保留 `None`（未声明）和 `{}`（显式使用 schema 默认值）的区别。
2. 配置加载校验 table 与支持的值类型，错误指出具体 manifest 路径；存储时做防御性复制，每次调用再复制嵌套值，防止某一 Run 修改后影响后续 Run。
3. sync invoke、async ainvoke、sync-only fallback 三条路径统一构建调用 kwargs：仅在显式提供 context 时传 `context=`，config/callbacks 不变；不能遗漏 to_thread 分支。
4. 映射交给 LangGraph 公共调用接口，由其 context_schema 构造 dataclass/Pydantic 等原生 Context；不在宿主导入 `react_agent.context.Context`，不调用 LangGraph 私有 `_coerce_context`。
5. 未声明 Context 时维持原生默认行为，不因存在 context_schema 就拒绝运行。显式空表可激活默认值；缺必填字段、未知字段、类型不符时依照 schema 行为报告清楚的配置错误，不给字段发明默认值。
6. 对绑定/旧接口不接受 context 的情况，调用前做能力校验，错误指向 `[adapter.context]`；不能先调用失败再去掉 context 重试，这可能执行两次业务。
7. 这次先支持 manifest 静态运行上下文，不把 KUMA payload 自动解析成 context，也不添加任意 Python import 字符串。非数据对象和复杂生命周期仍使用外层 binding。

### 验收

- 真实 LangGraph 图覆盖 dataclass、TypedDict、Pydantic Context；验证默认值、显式值和嵌套值。
- 区分不传 context 与传空表：默认字段能被初始化；旧的无 context binding 完全不变。
- sync、async、fallback 均拿到相同字段；callbacks 和 configurable.thread_id 未丢失。
- 连续 Run 的修改不串配置；非法类型、缺必填值报错包含配置来源；不发生第二次调用。
- #2 修复后用未修改的 ReAct 风格图做 host 端到端；同 manifest 在受控容器执行也通过。
- 扩展 `tests/test_langgraph_adapter.py`、`tests/observe/test_worker.py`，同步 `docs/Agents/Runtime.md` 与 adapter README。

**架构与无硬编码说明：** Context 是 LangGraph Adapter 的通用输入通道。`model`、`max_search_results` 只是 Agent 自己 schema 的字段，ABB 不列举它们、不重写它们；真实目标模型仍由现有 interceptor target 配置控制。

## 7. #5 — run / certify 缺少外部 registry 参数

**优先级：P2。代码落点：** `cli/features/run.py`、`certify.py`，必要的共享 parser/path helper，以及 `docs/CLI.md`。

### 修复步骤

1. 两个 parser 加入 `--registry PATH`，默认值保持当前 DEFAULT_REGISTRY_PATH；execute 显式传入已有 run/certify 的 registry_path。
2. 所有选中 Agent、状态筛选、认证更新都使用同一个已解析 registry 路径。不得读取外部配置后把 ready 写回内置 registry。
3. 复用 `load_registry` 的现有 workspace-root 定义（registry.parent.parent），不在本次修改其解析语义；文档说明外部 registry 布局。
4. 明确路径规则：显式输出参数仍相对调用方 cwd；certify 缺省产物继续相对 registry workspace；run 当前默认输出语义保持。env-file 的现有查找策略不因 registry 改变而悄悄切换，跨工作区用户可显式提供。
5. 认证结束的状态更新继续使用 expected_status 和原子替换，保留注释、字段顺序及其他 Agent。

### 验收

- 三个以上临时 Agent 覆盖 ready/adapting/disabled；在不同 cwd 调用外部 registry，run 仅选择外部 enabled+ready。
- certify 仅运行目标，完整成功后仅修改外部目标 status；内置 registry 文件哈希不变。
- 相对/绝对路径、空格、Unicode、registry 不存在、路径越界、并发状态变化均有测试。
- 缺省命令及 Python API 保持兼容；帮助信息、重跑路径提示指向同一 workspace。
- 扩展 `tests/test_cli.py`、`tests/test_cli_certify.py`、`tests/test_registry_status.py`。

**架构与无硬编码说明：** 把 CLI 参数接到已有 Python API，路径解析继续只有一个来源；不增加 external-agent 特殊 runner，也不根据目录名推断 Agent。

## 8. #6 — evaluate 丢弃 BenchmarkResult 与输出契约混淆

**优先级：P2。代码落点：** `cli/features/evaluate.py`、`cli/execution.py`、`cli/result_export.py`，复用 SuiteRunner/EvaluationRunner。

### 明确参数契约

- ABB 从每次 evaluate 开始就保存统一 JSON 结果；任何 SDK 都不例外。
- 新增 `--result-output PATH`：与 run/certify 的结果命名方式一致，为 ABB 标准 JSON 命名基址；未指定时使用 registry workspace 下的 `results/evaluate-<安全Agent标识>.json`，经现有 writer 生成唯一文件。
- 保留现有 `--output` 作为 SDK output 别名，help、提示和文档明确它不指定 ABB JSON 的位置。提示使用 `--result-output` 控制标准结果；SDK 私有配置的首选形式是 `--sdk-options`。
- 不根据 SDK 名字决定 `--output` 是文件还是目录；不声称能自动知道第三方 SDK 是否消费某个 kwargs。CLI 不再承诺此 SDK 选项必然创建文件。

### 修复步骤

1. 在 SDK 校验/执行前建立 ResultLogWriter，拿到可追踪的 suite_id；使用现有原子 JSON writer 和已定义事件 schema。
2. 将选择好的 EvaluationRunner 接入现有 SuiteRunner 和共享 CLI execution；evaluate 使用一个副本 registration 指定 case_count=1，不改 registry 中原有 case 数和 status。
3. 把 progress、step_started/completed/failed、agent_completed、suite_completed/failed 接到同一 writer。不能只在成功后把 BenchmarkResult 拼成结果，那样会丢中断及失败步骤。
4. 如果需要抽取共享执行函数，只抽现有 execution 模块内的记录/运行逻辑，避免复制 run 的选择菜单、viewer 交互、认证更新和 SDK handshake。
5. 保存标准 BenchmarkResult 中的 output、raw_output、report、SDK/run 身份；SDK 私有产物目录作为引用保留，不重新解析 `.kuma` 等内部格式。
6. evaluate 保持单次非交互结束：收到报告且执行正常返回 0（包括 Judge issue，沿用当前语义）；运行失败/无报告为 1，参数错误为 2，中断为 130。不要直接沿用 run_benchmark_once 的“Judge issue 返回 1”而造成隐式行为变更。
7. 写文件失败明确退出非零并提示路径；结果为空、不完整或失败不能打印“成功保存”。Ctrl+C 时保留已写事件，registry 不变。

### 验收

- 使用不写任何磁盘文件、无 KUMA 依赖的最小第三方 SDK：evaluate 仍写标准结果，含 Input/output/真实 Judge report，view 可读取。
- `--result-output` 在自定义位置落盘；重复执行不覆盖；同时传 SDK `--output` 时两者互不冲突。
- 注册配置 case_count>1，evaluate 仍只创建一个 Case，但消费该 Case 的全部 SDK Inputs；registry 字节不变。
- 覆盖启动失败、第二步失败、Judge 异常、无报告、权限错误、Ctrl+C，能看见中断前结果；提交不重试。
- KUMA 与第三方 plugin 仍收到原选项；run/certify 导出 schema 不回归；Judge issue 退出码符合上述契约。
- 扩展 `tests/observe/test_evaluation.py`、`tests/test_sdk_plugins.py`、`tests/test_viewer.py`，新增 evaluate CLI 结果测试。

**架构与无硬编码说明：** 结果文件属于 ABB CLI，私有 evidence 属于 SDK。通用结果源是 EvaluationRunner 的 BenchmarkResult，不使用 `if sdk == kuma`，不要求第三方实现 KUMA 文件夹结构。

## 9. #7 — Host 执行无 artifact_directory，Viewer 空白

**优先级：P2。代码落点：** `observe/` 共享 invocation 观察组件、host BenchmarkRunner、container worker、SDK composition root、`observe/view_api.py` 和前端 evidence 视图。

### 修复步骤

1. 从 container worker 中提取薄的、与 Docker/SDK 无关的“单次调用观察生命周期”：创建 TraceStore、按 framework 获取 callbacks、可选 ObservedStore、开始/结束/异常、flush。它不创建 Agent、不开网络、不调用 SDK。
2. host runner 和 container worker 都复用它；harness 通过注入的 observation factory 使用其能力，不直接堆叠 OTel/客户端库。无观察配置的 Python 调用保留轻量行为，CLI 默认注入 artifact root。
3. 每个 Case/SDK Run 创建独立安全生成的目录 ID，记录原始 SDK run_id 为 metadata；每个 Input 再建 invocation 目录。不得把第三方 run_id 原样拼入文件路径。
4. 复用 viewer 已接受的 `run.json` 和 `evaluation/inputs/0001/` 等契约；固定宽度序号仅为现有存储约定，不能用它替代真实 input_id。文件同时保存 agent_id、sdk_run_id、input_id、invocation_id。
5. 目录建立后立刻在 started progress 发出 artifact_directory，完成/失败 progress 保留引用。已有 sdk_run 分支也必须执行相同观察生命周期。
6. host 仅保存实际框架回调和现场产生的 OTel span。无拦截时明确 `network: unavailable / runtime_without_interceptor`；不创建伪造 network.jsonl。OTel 未安装时保存 unavailable 原因，framework 仍可查看。
7. 建立 additive evidence availability 字段：每类证据区分 available / unavailable / pending / failed / unknown，并带 reason。API/UI 根据能力和文件事实显示空态；“不支持”“尚未产出”“文件丢失”“旧格式未知”不能混成空白。
8. 标准 Input/output/Judge 来自 ABB 已取得的公共结果，可展示在评测页；第三方私有 Case/Judge 请求原文若没有提供，明确不可用，不捏造原始服务请求。
9. 跨步 callbacks 每次独立、用户 callbacks 合并而非覆盖；检查共享 TracerProvider 的 exporter 生命周期，避免多步反复添加 processor 导致重复/串写。外部 provider 不关闭，observer 自有 provider 负责 flush/shutdown。
10. 本次修复 host benchmark 的证据链，不顺带把 SDK-independent observe 命令扩成所有 runtime，也不增加宿主透明网络拦截。

### 验收

- 本地 SDK + 三步真实 StateGraph：SuiteRunCatalogAPI 列出运行，包含每步 framework 事件、最终 output/Judge，artifact_directory 从开始阶段就存在。
- 安装 OTel 时有真实父子 span；不安装时显示原因并保留框架轨迹；宿主无拦截时网络页显示“不支持该证据”，而不是“零次请求”。
- 两个 Agent、两个 Case、相同外部 run_id、恶意路径 run_id、多步输入均不串目录/回调/exporter，真实关联按身份字段而非时序。
- Agent 抛错、SDK 抛错、取消、导出器失败均保留已产生证据，run.json 有正确终态；观测错误和 Agent 业务错误独立表达。
- API 测试及浏览器检查验证四个 evidence 标签：有数据的展示，无数据的说明；旧结果没有 availability 字段仍可打开。
- 回归 `tests/observe/test_worker.py`、`test_otel.py`、`test_view_api.py`、`test_interactions.py`、`tests/test_benchmark_runner.py`；新增 host artifact 端到端用例。

**架构与无硬编码说明：** Docker 决定网络拦截能力，Observer 决定框架观测能力，SDK 决定其私有证据能力；UI 从结构化能力信息显示，不根据 Agent 名、SDK 名或 runtime 猜所有 tab 的内容。只提取一份共用观察生命周期，不新建第二个 worker 或评测 runner。

## 10. #8 — 新 checkout 的 Viewer 缺少前端构建产物

**优先级：P2。代码落点：** `cli/viewer.py`、`cli/features/view.py`、共享结果 footer/自动 viewer 启动，以及 README / CLI 文档。

### 修复步骤

1. 集中定义 viewer asset resolver 和 preflight，检查 index.html 及构建引用的本地 assets 是否存在。测试可以注入 asset root；不把开发者机器路径写进代码。
2. 显式 `view` 在开服务前发现缺失，返回清楚的非零错误及实际项目 web 目录的构建步骤：`npm ci`、`npm run build`。路径含空格时正确展示，不偷偷执行 npm 或联网安装。
3. run 自动打开 viewer 时缺少构建产物，只禁用本次 viewer 并提示，不影响评测和结果落盘。共享 execution 捕获明确的 ViewerUnavailable 错误，而不是泛化吞掉所有异常。
4. 完成后的 footer 只有在资产可用时承诺直接打开；否则展示“结果已保存”和构建后查看步骤。运行中资源被删除仍保留明确 HTTP 503，不出现无说明白页。
5. README 增加首次源码安装步骤，CLI 文档明确“运行预构建 Viewer 不需要 Node；从源码构建需要 Node/npm”。本次不自动发布 wheel；如果当前交付包含 wheel，发布验收必须额外确保预构建 assets 作为包资源交付，不能声称一个不含 UI 的 wheel 支持开箱即用 viewer。
6. 不提交整个 node_modules，不把 dist 的 gitignore 删除作为修复；继续使用现有 Vite 锁文件构建。

### 验收

- 临时空 asset root：显式 view 非零并输出可执行步骤，无僵尸 server/thread；run 评测仍完成并保存 JSON。
- 从无 dist/node_modules 的干净目录执行 `npm ci && npm run build`，然后 view 返回 200，JS/CSS 可加载、数据 API 正常，浏览器无资源 404。
- 预构建 assets 存在、运行时 PATH 没有 Node：viewer 正常。
- cwd 不在仓库、路径含空格、index 存在但 chunk 丢失、启动后资产删除：错误清晰。
- 回归 `tests/test_viewer.py`、`tests/test_cli.py`，并执行前端构建与实际页面检查。

**架构与无硬编码说明：** Viewer 负责分发已构建资源，CLI 负责预检和提示；评测不依赖 npm。使用共享资产定位和现有部署契约，不按开发平台、用户目录或某个 dist hash 分支。

## 11. #9 — Registry、文档、测试的 ready 状态冲突

**优先级：P2。代码落点：** `tests/test_registry.py`、`resources/registry.toml`（仅证据需要时）、Company 外层说明、`docs/Agents/Layout.md` / `Certify.md`，必要的认证结果说明。

### 修复步骤

1. 先核对实际认证证据：是否存在完整 certify 结果、实际源码 revision/manifest、所选 SDK、全部请求 Cases、运行错误、Judge 返回以及对应 artifact。已有 observe 成功或 evaluate 成功可作辅助证据，不自动等同 certify 已完成。
2. 状态按固定规则处理：若能验证当前版本的认证完成，保留 ready 并记录证据路径、日期、范围；若没有足够依据，本修复将其设为 adapting，并注明需后续正式认证。**不得仅因旧测试期待 adapting 或 Judge issue 就降级。** 不伪造认证日志，也不在计划编写阶段改状态。
3. 将“ready() 的筛选语义”测试改成临时 Registry fixture，包含 enabled/disabled 和 ready/adapting/blocked 等组合；测试固定业务规则，不固定生产 Agent 数量和具体名称。
4. 生产目录测试检查真实不变量：完整注册 unit 的 ID、路径、manifest 一致；生产目录中完整 unit 与 Registry 的登记关系；排除明确缓存文件。发现未完成目录应报告具体缺失项，不靠 `目录恰好等于 {Company}` 判断。
5. Deer Flow 当前已经被删除，保留用户现有操作。若之后存在未完成下载物，应按已有 Factory/下载区约定管理，不为修测试补空配置、注册假 Agent 或恢复目录。
6. 更新过时 Company requirement 与 Layout 的“未配置、未运行”段落，区分历史迁移结论和当前证据。通用 Layout 文档以布局规则为主，具体 readiness 证据放 Agent 外层说明或认证产物中。
7. 保留 certify 的原子状态更新及并发保护；本项不增加“每次 load_registry 都去联网复核认证”的机制，也不重新定义 ready 为质量通过。

### 验收

- `tests/test_registry.py` 不再因正常添加/移除完整 Agent 而失败；fixture 真正验证 disabled ready 被排除、enabled adapting 被排除。
- 初始 adapting，完整执行 + Judge issue 仍可 ready；启动/调用失败、缺少 Case、取消不晋级；并发状态变更不会覆盖。
- 注册表、Agent 当前状态说明和认证依据一致；所引用证据实际可读取，不能只写一个不存在的文件名。
- 添加一个名称随机的完整 Agent，通用测试无需修改；不完整 unit 给出准确错误。
- 回归 `tests/test_registry.py`、`tests/test_cli_certify.py`、`tests/test_registry_status.py`。

**架构与无硬编码说明：** ready 的语义由通用状态流程决定，具体值由认证证据决定。生产清单是数据，不是测试逻辑；不把 Company 名称或“只有一个 Agent”写进通用断言。

## 12. #10 — in_process Agent 被强制要求 Dockerfile

**优先级：P2。代码落点：** `harness/registry.py`、`runtime/agentcontainer/config.py`、RuntimeFactory 使用的纯配置部分和文档。

### 修复步骤

1. 将现有 runtime/build/launch 的纯结构解析与 secret/env 解析分开；复用小型共享配置值对象或验证函数，不为了 Registry 调用完整 `AgentContainerConfig.from_agent_dir()`，因为后者会要求真实密钥。
2. Registry 保留身份、source、requirement 等通用校验；runtime 类型从同一纯解析器获得，缺省仍是 in_process，未知类型明确拒绝。
3. in_process 不验证 Dockerfile/build/launch，不要求创建任何占位文件；仍验证该 unit 的通用有效性。
4. docker 才验证 build.context 是目录、Dockerfile 存在且是文件、launch.argv 有效；Dockerfile 相对已解析的 build.context，而不是 unit 根目录。保留当前路径越界和 symlink 约束，错误指出对应 manifest 字段。
5. RuntimeFactory 与实际构建也使用同一解析结果或同一解析逻辑，避免 Registry 通过但 Runtime 用另一套默认值/路径失败。
6. 纯解析不能启动 Docker、联网、导入 Agent 或读取密钥。运行时 secret 仍只在准备执行时解析，方便无凭据列出 Agent。
7. 更新 Layout/Factory 文档，Dockerfile 标记为仅 docker 所需；不把整个 manifest 校验框架重写成新 DSL 或全新插件系统。

### 验收

- 没有 Dockerfile 的 in_process unit 正常注册并执行最小本地图；缺省 runtime 行为仍是 in_process。
- docker 缺 Dockerfile 报错；自定义文件名、嵌套 build.context 正确；目录冒充文件、`../` 越界、symlink 逃逸被拒绝。
- 没有真实模型/Tavily 密钥也能完成结构校验；开始执行时才报告缺密钥。
- Registry 与 Docker builder 对同一 manifest 的路径解析一致；Company 现有配置无需更改。
- 扩展 `tests/test_registry.py`、`tests/test_container_runtime.py`、`tests/test_docker_runtime.py`。

**架构与无硬编码说明：** 要求由 runtime 能力决定，路径由 manifest 决定，默认值与 RuntimeFactory 一致；不写死文件名、Agent ID，也不按 Dockerfile 是否碰巧存在猜 runtime。

## 13. 联合验收与完成定义

### 验收层级

| 层级 | 内容 | 通过条件 |
| --- | --- | --- |
| L1：公开离线回归 | 临时 Registry、本地 SDK、真实最小图、公共结果/存储/API | 不需要私有 SDK、真实密钥、Docker；每个 bug 的正反例可独立运行 |
| L2：真实客户端受控网络 | 实际 OpenAI/LangChain/Tavily 客户端 → loopback/受控 TLS 上游 | 正确调用、Context、关联；没有额外业务替身逻辑；不调用付费 API |
| L3：Docker | native Linux 必选、Desktop 回归；原 policy 和受控 Agent | 启动、CA、真实请求、结果、关联、清理全部通过 |
| L4：正式 SDK 集成 | 显式提供 KUMA 安装及凭据时运行 | Case/Input/Submission/Judge 身份与完整证据对应；不把离线 SDK 当正式判决 |

“离线”不一定意味着不监听本机端口；loopback 测试需要本地监听权限。构建镜像/前端可能下载依赖，须与业务 API 验收区分。报告中的 258/5/19 是历史统计，不作为当前通过数量。

### 三个必须跑通的场景

1. **外部工作区完整生命周期：** 不含 Dockerfile 的 async LangGraph Agent，带普通 Context；临时本地 SDK 提供三个 Inputs；从外部 registry certify → ready → run → evaluate，使用不同 cwd；ABB JSON、host 框架证据与 viewer 空态完整；内置 registry 和上游源码哈希不变。
2. **真实受控拦截链：** native Linux Docker、非 root 宿主；原版 ReAct 风格图运行一次模型→工具→模型流程；验证 CA 私钥不出容器，两个模型请求和工具请求各自链接真实节点，所有内部 header 在上游前移除。
3. **失败与分发链：** 第二个 Input 抛错或执行中断，保留第一步和失败证据、不晋级；未构建前端时给出明确步骤，构建后同一产物可打开；无 Node 的运行环境能使用预构建 UI。

### 每项交付清单

- 修复代码只落在所属层；必要的共享修改说明调用方和兼容影响。
- 针对真实缺陷的回归测试先失败、修复后通过；不通过检查源码字符串或简单 mock 返回值替代行为验收。
- 记录实际执行命令、环境/版本、通过/失败/跳过数、产物路径。跳过、未安装依赖、无法使用 Linux 环境均不是通过。
- 更新对应 CLI/Runtime/SDK/Observe 文档和参数 help；本计划中的接口新增在实现时同步到公共契约。
- 上游 Agent 文件无改动；没有特定 Agent/模型/用户名分支；没有补造证据、替换原工具或复制 SDK handshake。
- 无关已存在失败单独登记，不删测试、不把依赖缺失伪装通过；本轮引入的失败必须消除。
- 每个编号可独立评审；依赖前序编号的提交明确说明依赖。全部联合验收完成后才关闭十项问题。

## 14. 实施状态

| 问题 | 实现 | 已完成的验收 / 边界 |
| --- | --- | --- |
| #1 | 容器 tmpfs CA；仅导出校验后的公有证书 | Docker Desktop 真启动、导出、失败清理；原生 Linux 待实机验证 |
| #2 | Run 级异步生命周期 | 多 Input 同循环、同步回退、异常、取消、aclose |
| #3 | 四种传输 hook + 关联缺口提示 | 真实传输/重定向/并发，以及本机 OpenAI、Tavily SDK；不代表所有版本 |
| #4 | 可选 adapter.context | 深复制、真实 LangGraph dataclass/Pydantic、同步/异步 |
| #5 | run/certify 外部 Registry | 不同 cwd 的真实 CLI certify→run；只更新选定 Registry |
| #6 | evaluate 标准结果归档 | 第三方 SDK、1 Case 3 Inputs、pass/issue、公有结果、脱敏 |
| #7 | Host/worker 复用观察生命周期 | 真实框架轨迹、OTel、公共 Judge、缺失来源、失败产物、共享 provider |
| #8 | 前端资产预检 | 缺 index/引用资源、HTTP Viewer 回归、前端测试和构建；浏览器自动验收受客户端限制 |
| #9 | Registry/文档/测试一致 | 缺少保留的认证记录，Company 暂为 adapting；认证规则保持不变 |
| #10 | runtime 区分和纯结构校验 | 无 Dockerfile 的 in_process、相对 context、自定义 Dockerfile、路径越界、argv |

CA 实施调整：Docker 实测发现 `docker cp` 无法可靠读取 live tmpfs；最终通过
`docker exec cat` 读取协议指定的单个公有 PEM，由宿主机校验并原子写入。
不导出目录、不增加 capability，不引入固定宿主 UID。
