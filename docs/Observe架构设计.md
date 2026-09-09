# Observe 架构设计与预计数据流

状态：设计草案，2026-09-09。依据当前 ABB 工作区、Wangyi `0803fe85` 和 Company 上游源码核对；本轮不实现 CLI/网页、不启动容器、不调用模型或评测 SDK。

实际工作区为 `C:/Song_startup/benchmark/AgentBehaviorBench0.0`；React + Vite 将位于该项目的 `web/`。本文独立于《用户的想法》。

## 1. 本轮要建立什么

`agentbench observe` 读取注册表，展示所有 `enabled=true` 的 Agent，以 1 开始编号。用户选择后，ABB 启动 Agent 和观察网页，持续收集运行信息。首个里程碑停在“输入 1，Company 后端及采集链路就绪”，不自动发起公司研究。

入口假设：沿用此前用户选择的 Company 原生 HTTP 后端。Wangyi 可借鉴的是“容器内运行原 Agent、在实际执行处采集”，此次不照搬其 SDK 多步评测或直接 Graph 驱动。若改选容器内直接调用 Graph，只替换 Company Driver/启动绑定，下面的会话、存储和网页协议保持一致。

启动与执行分开：输入 1 启动观察会话；后续网页提交公司名才创建研究任务。启动时可以产生真实启动 span、日志和采集连通性记录，但不能显示虚构的研究节点、搜索或 LLM 调用。

## 2. CLI 行为

```text
agentbench observe
    → 读取 resources/registry.toml 的目录信息
    → 筛选 enabled 项，按注册表顺序形成选择快照
    → 显示：
        1. 01 Company Research Agent [adapting]
    → 输入 1
    → 解析选中 Agent 的源码、Docker、启动和 observation 配置
    → 校验配置并创建 observation session
    → 启动观察服务、存储及遥测接收端
    → 准备 Interceptor、构建镜像、启动 Agent 容器
    → 验证原服务就绪及遥测上报
    → 网页显示“后端已启动 / 采集已连接 / 等待任务”
    → CLI 保持运行；Ctrl+C 收尾
```

- `observe` 使用 enabled，不使用 `ready()`；adapting 可以选择，仍必须通过运行配置校验。观察成功不会自动修改注册表状态。
- 数字只代表本次列表位置，持久标识始终使用 `agent_id`。非法、零、越界输入重新提示；`q` 退出；没有 enabled 项时明确结束。
- 列表包含 display name、agent_id、framework、status；缺观察配置的 Agent 可见，选择后给出具体缺项。
- CLI 只解析参数、展示列表和调用 `ObservationService`。Python 用户可直接调用同一个服务，不通过 CLI。
- 当前 load_registry 会深度校验所有 Agent 目录，任何一项损坏都会阻止列表出现。实现时抽出“读取注册目录 / 解析选中 Agent”两步：全局仍校验 schema 和重复 ID，单 Agent 文件/启动配置在选择后校验；旧 load_registry 可组合两步保持原行为。失效的未选 Agent 不应阻止观察其他 Agent。
- 复用现有 CommandFeature 注册机制，增加 `features/observe.py`；实现时同步更新 CLI 文档、帮助和测试。此次不替换已有 run/view/certify 行为。

## 3. 运行部署图

```text
宿主机：agentbench observe（Python）
  ├─ CLI：编号选择、状态输出、退出管理
  └─ ObservationService
      ├─ Runtime：Docker 构建、启动、端点、停止
      ├─ Driver：Agent 原生输入、任务、进度、结果
      ├─ HTTP API + SSE + React 静态资源
      ├─ 遥测接收：OTLP traces + ABB 运行事件
      └─ SQLite + 内容附件
                    ↑                     ↑
                    │                     │
Agent 容器           │               可信 Interceptor 容器
  Python bootstrap  │                 ├─ 模型协议转换/转发 → OpenRouter
    → 安装观测 hooks ─┘                 └─ 请求/响应记录及关联信息
    → 原 application:app
      → POST /research
        → process_research
          → Graph.run
            → 模型客户端 ────────────────┘
            → 真实 Tavily

React 浏览器 ← HTTP 查询 / SSE 更新 → ObservationService
```

第一版采用一个宿主机观察进程，复用已有 Interceptor 容器，再运行一个 Agent 容器。OTel instrumentation 必须在 Agent 进程内工作；接收、存储位于宿主机。评测 SDK 不进入 observe 的依赖或执行路径，未来单独接入。

## 4. 模块边界与现有代码复用

| 模块 | 职责 | 当前基础与改动 |
|---|---|---|
| Registry | 找到、列出 Agent 单元 | 复用注册模型及 enabled 语义，拆开目录读取与选中项解析 |
| ObservationService | 会话、任务、生命周期、事件协调 | 新增；不复用 BenchmarkRunner 的 SDK 驱动循环 |
| DockerRuntime | 镜像、进程、网络、凭据、服务端点 | 复用；补启动上下文、端口、日志订阅、优雅停止 |
| Driver | 描述输入/能力，调用 Agent，取得结果 | 新增首个 Company HTTP Driver；不把 Company 路由写进核心 |
| Observer | 框架、HTTP、模型、工具插桩 | 新增容器内轻量包；LangGraph callbacks 是采集插件，与 Driver 分离 |
| Store/API | 验证、保存、查询、订阅 | 新增 SQLite 与 API；不把旧结果 JSON 整文重写器作为实时存储 |
| React | Agent 信息、状态、调用树、详情 | 在 web/ 建 Vite + React + TypeScript；不解析 Docker 日志 |
| Model Interceptor | 模型统一出口及实际请求记录 | 复用独立服务；补上下文关联、流式片段和网络配置 |

建议最小代码组织，按职责而非按每种事件继续拆服务：

```text
agentbench/cli/features/observe.py
agentbench/observation/
    service.py       # session/task orchestration
    models.py        # 协议模型与版本
    api.py           # UI API、SSE、遥测接收应用
    store.py         # SQLite、事件游标、附件
    drivers/         # 原生调用接口及实现
agentbench/telemetry/ # OTel 接收/投影、Interceptor 桥接
services/agent-observer/  # 轻量容器内 bootstrap、callbacks、工具 hooks
resources/agents/01-company-research-agent/
    agent/           # 上游源码
    agent.toml
    requirement.md
    Dockerfile
    integration/     # Company 的 Driver 配置、容器 bootstrap 绑定
web/
    package.json
    vite.config.ts
    src/             # React 页面、状态归并、生成的协议类型
    dist/            # 构建产物
```

容器内 observer 不依赖完整 ABB harness 或 Defuze SDK；打成独立 wheel 安装，避免导入宿主机依赖。Company 专属 hooks 位于上游源码目录之外，记录其版本和改动范围。

## 5. Runtime、Driver 与 Agent 配置

Registry 只负责发现，agent.toml 是运行配置入口；继续使用现有 source/runtime/build/launch/llm_interception。新增 observation binding、服务端口、就绪探测和观测插件声明，字段正式实现时另定 schema，不把当前文件解释成已经支持这些字段。

- 配置描述数据：启动 argv、workdir、环境变量名称、端口、插件名、Driver 引用。
- Python Driver 处理复杂行为：提交研究、读取 job_id、消费 SSE、读取报告。不要用 TOML 发明循环、条件、脚本或任意字段映射语言。
- 通用核心的 Driver 接口为 `describe / check_ready / submit / watch / result / close`；`cancel / resume / reset` 是可选能力。一次性命令也可以由 submit 启动，watch 等待退出；不要求未来 Agent 一律提供 HTTP。
- Driver 得到 RuntimeHandle（进程状态、服务端点、日志/产物访问）；不能直接改写 Docker 命令。Runtime 不解析业务输入，也不把 stdout 当作响应。
- `describe` 输出输入 schema、能力、来源及采集覆盖情况。声明支持、静态发现、本次实际调用分别标注；暂未加载的图显示未发现。
- 第一版仅 Company 真实 Agent；用独立离线样本验证 Python/CLI Driver 的扩展边界，当前不增加真实注册 Agent。

Company 的具体绑定：

```text
容器 Python bootstrap
    → 初始化 OTel provider、事件队列和 HTTP 上下文传播
    → 安装 Company 后台任务与 Graph.run hooks
    → 加载原 application:app
    → Uvicorn 单进程启动后端

check_ready  → GET /，检查 Alive 响应
submit       → POST /research，原样传 company/company_url/industry/hq_location
watch        → GET /research/{job_id}/stream，仅一个上游消费者
result       → GET /research/{job_id}/report
```

`GET /research/{job_id}` 在原项目无 MongoDB 时返回 501，不用它做就绪检查或默认轮询。单进程避免其内存 job_status 在多个 worker 间分裂；第一版任务执行限额为 1，其余请求明确拒绝或排队，内部四研究分支仍正常并行。

## 6. 两种生命周期与 ID

| 标识 | 含义 |
|---|---|
| agent_id | 注册表中的稳定 Agent 标识 |
| session_id | 用户选中 Agent 后启动的一次观察环境 |
| task_id | 在该环境中提交的一次研究任务 |
| native_task_id | 原后端返回的 job_id；不强制其改名 |
| trace_id / span_id | OTel 调用关联；一个任务可关联多条 trace，不能强求所有源都同一条 |
| call_id | Interceptor 的一次实际网络调用，显式关联到 span |
| seq | Store 为同一 session 已提交事件分配的递增序号 |

```text
session: preparing → starting → ready → stopping → stopped
                                 ↘ degraded
          任何启动阶段失败 → failed → 清理资源

task: queued → running → succeeded / failed / interrupted
```

session 的 ready 是运行状态，不是 registry.ready 认证。Agent API 可用、telemetry 可用、业务执行配置可用分别记录；不能只因容器 PID 存在就显示全部就绪。

启动 spans 无 task_id；研究 spans 有 task_id。任务成功以原后端报告/状态为准，span 的 OTel UNSET 不等同业务成功。原 process_research 捕获异常后可能不抛出，Company hook 必须读取终态，不能只看协程正常返回。

## 7. 三层协议

Agent 不需要遵守统一输入输出协议。统一的是 ABB 自己的控制 API、遥测入口和浏览器数据协议。

### A. React 与观察服务：HTTP + SSE

API 统一前缀 `/api/v1`：

| 接口 | 用途 |
|---|---|
| GET /agents | 查询 Agent 信息与能力 |
| GET /sessions/{id}/snapshot | 获取会话、任务、span 投影与一致的事件水位 |
| GET /sessions/{id}/events | SSE，支持 after 与 Last-Event-ID |
| POST /sessions/{id}/tasks | 提交原生输入，返回 task_id；请求带幂等键 |
| GET /tasks/{id} | 任务状态、native_task_id、结果引用 |
| GET /tasks/{id}/spans | 分页查询 spans |
| GET /spans/{trace_id}/{span_id} | 获取单节点详情及大内容引用 |
| GET /artifacts/{id} | 按 ID 获取报告、请求响应等内容 |
| POST /sessions/{id}/stop | 停止本次观察会话；不等于原生任务可取消 |

Browser 初始快照和 cursor 必须来自同一数据库读取事务；随后订阅 cursor 之后的事件。SSE 自动重连携带 Last-Event-ID，刷新页面则重新取快照。服务端维护每个订阅者自己的游标，绝不共享 pop 队列。参考 [SSE 事件 ID](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)。

### B. Agent 与观察服务：OTLP + 运行事件

- 完成的 spans 使用标准 OTLP/HTTP protobuf `POST /v1/traces`，基于官方 proto 解码、校验、响应；第一版只声明支持 traces/http-protobuf，其他内容类型明确拒绝。
- 运行开始、业务进度、token 片段等走 ABB 事件入口 `POST /ingest/v1/events`，批量 JSON 数组；这是 ABB observer 的协议，不是强加给 Agent 的协议。
- 两条通道共享 session/task/trace/span 标识。OTel 完成记录更新已有 span，不再创建第二个节点。
- `SpanProcessor.on_start` 仅向有界队列放运行通知，不同步发网络请求；后台发送线程负责重试。最终 spans 由 exporter 发送。开始通知与结束 span 可乱序，前端/Store 必须正确归并。
- 每个进程只初始化一次 OTel provider，任务靠上下文隔离，不为每次任务重复设置全局 provider；遥测发送自身排除插桩，避免递归产生遥测请求 spans。

协议依据：[OTLP](https://opentelemetry.io/docs/specs/otlp/)、[Python SpanProcessor](https://opentelemetry-python.readthedocs.io/en/stable/sdk/trace.html)。不把 ABB 运行事件称作 OTLP。

### C. 可扩展的浏览器事件 envelope

```json
{
  "schema_version": "1.0",
  "event_id": "evt_...",
  "seq": 42,
  "type": "span.started",
  "observed_at": "2026-09-09T12:00:00.000Z",
  "received_at": "2026-09-09T12:00:00.030Z",
  "agent_id": "company-research-agent",
  "session_id": "obs_...",
  "task_id": "task_...",
  "source": {"kind": "langgraph", "instance_id": "process_..."},
  "trace_id": "32位十六进制值",
  "span_id": "16位十六进制值",
  "parent_span_id": null,
  "payload": {"name": "company_analyst", "category": "node"}
}
```

示例 ID 是占位说明，不是可用 OTLP ID。event_id 由生产方生成并在重试时保持；seq 和 received_at 由服务端分配，不接受客户端覆盖。不同事件使用不同 payload schema，不能把所有未来字段塞进同一对象。

首批事件族：`session.* / task.* / span.started / span.completed / llm.* / tool.* / log.record / artifact.created / capability.discovered / telemetry.gap`。未来可新增 metrics、文件、浏览器观察类型，无需修改 Agent 接入协议。

Python 模型/JSON Schema 作为协议源，生成 TypeScript 类型；前后端契约检查约束必填字段和版本。小版本只做兼容性增加；不支持的事件保留原始 payload，并在网页通用事件区展示，不导致整页崩溃。

## 8. Trace 关联与覆盖

```text
ABB 创建 task_id + 任务根 span
    → HTTP 请求携带 W3C traceparent 和受控的 task 关联字段
    → 原后端请求 instrumentation 提取上下文
    → 后台 process_research hook 保留上下文及 job_id
    → Graph.run 注入 callbacks
       ├─ node spans（保留 run_id / parent_run_id 的关联）
       ├─ LLM spans + streaming chunks
       └─ Tavily search/extract/crawl spans
           → HTTP client span
             → Interceptor 接收上下文并生成自己的 span/call_id
```

后台任务 span 覆盖完整研究时间，不随 POST 响应结束。允许子 span 比请求 span 更晚结束；task 根 span 一直保留至任务终态。ContextVar 按任务隔离，不能用进程级 current_task 变量；callback 父子映射与异步 task 的当前上下文都要处理。跨进程传播使用 inject/extract，不按时间相近猜父节点。参考 [OTel Python 上下文传播](https://opentelemetry.io/docs/languages/python/propagation/)。

Company hook 在 bootstrap 中安装，导入应用前完成必要绑定；对 Graph.run 合并原 config/callbacks，不覆盖原输入与状态。Tavily 是直接 SDK 调用，不能只等 LangChain on_tool 回调。框架节点、模型语义调用、HTTP 请求是不同层：同一模型调用可有多个重试 HTTP 请求，UI 按关联展示，token 计数明确来源避免重复累加。

Interceptor 在转发前读取并记录上下文，再剥离 ABB 私有任务字段和内部传播信息，避免无必要地传给外部服务；搜索客户端同样限制私有上下文出口。若某个客户端无法传播，显示未关联，不制造随机父节点拼成完整树。

第一版覆盖清单：启动、任务根、Graph 节点、LLM、Tavily、HTTP 边界、错误、报告。采集方式、未覆盖项、截断/丢弃量均可查询；不承诺未插桩进程、模型内部推理或任意工具自动可见。观测代码不重试业务调用、不改搜索结果，只记录其实际发生。

## 9. 存储、重连与失败处理

使用宿主机 SQLite（单 writer、WAL）保存 sessions/tasks/events/spans/artifacts。大请求、响应和报告存内容文件，以 ID 引用；网页按需加载。原始遥测与 UI 投影分开，不将未来 Judge 的证据裁剪反向应用于原始观测数据。

- 先校验/脱敏/写库，提交后再推送；事件 seq 与投影在同一事务更新。这里的“原始”指保留源结构的可保存数据，不代表密钥原文。
- 生产者重试按 source.instance_id + event_id 去重；OTLP 完成 span 按 session/trace_id/span_id 幂等接收，保留冲突诊断。开始事件晚到不能把 completed 覆盖成 running。
- 源时间用于展示耗时/时间线，接收序号用于回放；跨机器时钟偏差标识，不以收到顺序推断因果。
- exporter 有界缓存与有限重试；满队列、落盘失败、断流以独立诊断和 telemetry.gap 暴露。不得承诺进程硬杀时零丢失。存储不可用时不返回虚假的持久化成功。
- 慢网页订阅者断开后按游标回放，不能阻塞 Agent；事件若已过保留窗口，明确通知重取 snapshot。
- POST task 使用幂等键避免双击重复执行；若原后端已接受但响应丢失，先按 hook 关联记录对账，不自动重试产生第二份研究。无法确认时标记 dispatch_unknown。
- Ctrl+C：停止新任务 → 尝试 Agent 优雅退出/observer flush → 限时排空与保存 → 清理容器/网络 → 停接收服务。被终止任务记 interrupted；未正常结束的 spans 保留 incomplete。
- 宿主机崩溃后的下次启动，根据 session/container labels 检查遗留进程，状态标记 orphaned/interrupted，供用户恢复观察或清理；不自动重发旧任务。只有内存状态的原 Company 后端不能宣称支持断点续跑。

## 10. Docker 和当前 Company 的实际障碍

1. 当前 manifest 没有 launch 和 llm_interception；Dockerfile 也未安装 observer。这些是首阶段改动，不是调注册表 ready 就能解决。
2. 现有 runtime 使用 `--network container:<interceptor>`；Agent 后端的端口要发布在网络命名空间所属的 Interceptor 容器上，再由 RuntimeHandle 返回实际宿主机端口。UI 不直连这个端口。
3. UI/控制 API 仅监听 loopback。另设只有 ingest 路由的遥测监听应用，供容器访问，使用每 session 的写入 token；不向容器开放停止任意 session 等管理 API。Docker Desktop 用可达宿主机地址，Linux 通过显式 host-gateway 配置；必须用启动 span 实测连通，不假设容器 localhost 就是宿主机。
4. 现有 Interceptor 对非 root 的 80/443 做重定向。遥测端点、业务端口和真实搜索须按实际规则配置、验证；不能为了接遥测取消模型拦截。大消息限额和 token 的 session 绑定由接收端强制校验。
5. 原应用导入时创建相对路径 pdfs。将工作目录设为可写的 `/tmp/abb-work`，通过 PYTHONPATH 指向只读 `/opt/agent`，bootstrap 提前创建工作目录；不使整个根文件系统可写。
6. 原 application.py 会读取项目 .env 且 override=True。构建上下文排除该文件及上游密钥；以受控环境注入。已有模板保留变量名，永不把真实凭据写进镜像或页面。
7. 原 briefing 使用 ChatGoogleGenerativeAI，但当前 Interceptor 只支持 OpenAI Chat/Responses 与 Anthropic。真实研究前必须补齐 Gemini 协议兼容（包含流式响应回译），或另行明确记录并选择客户端替换。建议按现有协议插件边界补兼容；不能静默直连 Gemini 或把未知参数丢弃后宣称原生行为未变。启动就绪不代表这条模型路径已验证。
8. Tavily 保留真实 search/extract/crawl，不使用 Wangyi 的固定 OpenAI stub。启动阶段只检查运行所需配置，不发模型/搜索请求；业务执行前检查 Tavily 配置与所有模型路由。配置存在与在线凭据有效分别展示。
9. Observer 与 Agent 依赖版本需要镜像内验证，不能只测试宿主机。构建记录上游 revision、observer wheel 版本、镜像摘要、配置指纹与模型重定向；配置快照脱敏。

## 11. React 页面和完整预计数据流

首版页面：Agent 信息及来源、环境/采集状态、任务列表、调用树/时间线、选中节点详情、模型请求响应、工具调用、日志和报告。启动阶段显示环境及真实启动记录；没有任务时业务区为空。

执行图结构与实际 trace 分开：静态图可以有尚未运行的节点，trace 只显示发生过的调用。长 span、并行分支、失败和缺失父节点要有明确表现。大输入输出折叠并按需获取；模型流式片段按调用 ID 聚合并批量刷新，最终输出保留独立版本，避免片段重传重复拼接。

React 使用类型化 API 客户端、单独的 SSE 连接层及按 ID 归并的状态。组件不理解 Company job_status、不读取 SDK 内部对象。未知事件可通用查看；输入表单先支持 Company schema，同时保留 schema 驱动的 JSON 输入。

请求、工具输出和报告以文本或经过清理的 Markdown 渲染，不执行 Agent 返回的 HTML/脚本；控制请求校验同源及会话授权，遥测写入凭据不具备管理 API 权限。采集密钥在入库前去除，截断正文附原大小和截断标记。

开发使用 Vite dev server 代理 `/api`；日常 observe 由 Python 服务提供已构建 dist，无需用户额外启动 npm。构建产物随 Python 包发布，并验证资源路径；旧 view 页面需保留兼容入口或迁到 legacy 子目录，不能在改 web/ 时意外破坏旧结果查看。参考 [Vite 后端集成](https://vite.dev/guide/backend-integration.html)。

```text
后续一次真实研究：
React 输入公司名称
    → POST /api/v1/sessions/{session_id}/tasks
    → Store 创建 task_id；ObservationService 建立任务上下文
    → Company Driver POST 原 /research（携带 trace context）
    → 原后端返回 job_id；ABB 绑定 task_id ↔ job_id
    → 后台 Graph 执行研究
       ├─ 模型请求 → Interceptor → OpenRouter → 返回模型结果
       ├─ Tavily → 真实资料
       ├─ 运行开始/进度 → 事件入口
       └─ 完成 spans → OTLP 入口
    → ABB Driver 单次消费原业务 SSE，并取得最终报告
    → Store 保存源事件、spans、报告与任务终态
    → SSE 推送已提交事件
    → React 实时归并节点、调用关系、内容与报告
```

用户打开第二个网页或刷新，只查询 Store 和订阅 ABB SSE，不再连接原 Agent 的消费式 SSE。浏览器关闭不自动取消后台任务。

## 12. 实现顺序与验收边界

### 第一阶段：选择 1 后启动，作为下一次讨论的停点

- 注册表展示 enabled 项，编号从 1 开始；现有 Company adapting 仍可选择。
- observe/service、最小 SQLite/event API、Vite 页面骨架与容器 bootstrap 一起形成闭环。
- Company 原后端启动，GET / 通过；容器发出真实启动 span，经 OTLP 到 Store、再到 React。网页呈现启动信息与覆盖声明，不发起研究。
- 业务配置不足或模型协议未就绪分别显示；不能把尚未具备研究能力显示成研究可用。
- 用独立离线样本验证进程内运行事件实时到达、结束 span 归并、重连及 Ctrl+C 清理；对 Company 仅做不调用模型的启动验证。
- 达到此处停下讨论，不自动提交 OpenAI 或其他公司作为测试输入。

### 第二阶段：真实研究与完整业务 trace

- Company HTTP Driver、后台任务绑定、Graph/Tavily/模型插桩。
- 补全所有模型到 OpenRouter 的兼容路径，处理只读文件系统和真实搜索依赖。
- 输入公司名取得真实报告；核对节点、搜索参数/返回、LLM 请求/响应以及并行父子关系。

### 第三阶段：可靠性和更多观察信息

- 两个独立任务 ID 的串线隔离测试、源乱序/重传、慢网页、进程异常、存储失败。
- 扩展资源指标、文件、更多框架/Driver；未来 SDK 或 AgentRx 通过保存的证据或同容器插件接入，不反过来绑住 observe。

## 13. 参考项目与具体代码依据

Wangyi：参考 `015/runtime/entrypoint.py` 的 callbacks 接入位置、原始 spans 与 SDK evidence 的区分。不复制固定搜索、文本塞 company、硬编码 job/thread ID。SDK 可选接入不属于第一阶段。

AgentRx：本地 README 和 `agentrx/ir/trajectory_ir.py` 表明其入口是已有轨迹，经过 IR → invariants → check → judge → report。可借鉴“原始轨迹与分析视图分离”，以后输出一份 trajectory 给它；它不提供本次所需的 Agent 生命周期或实时 OTLP 接收层。

ABB 主要依据：

- [CLI 注册机制](../agentbench/cli/features/__init__.py)
- [注册表与 enabled](../agentbench/harness/registry.py)
- [Docker 启动和网络](../agentbench/runtime/docker/runtime.py)
- [DockerSession 生命周期](../agentbench/runtime/docker/session.py)
- [现有模型事件](../agentbench/runtime/interception/trace.py)
- [当前 Company 配置](../resources/agents/01-company-research-agent/agent.toml)
- [原 Company API 和后台任务](../resources/agents/01-company-research-agent/agent/application.py)
- [原 Graph.run](../resources/agents/01-company-research-agent/agent/backend/graph.py)

以上是待实施架构，不是现有功能或运行成功声明。
