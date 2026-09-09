# Agent 执行基础：三步实施与验收计划

状态：计划，尚未实施或运行测试。2026-09-09。

范围：①接通容器内 Adapter 执行；②补齐 Docker 启动与输入输出交付；③原客户端经 Interceptor 访问 OpenRouter，Tavily 真实搜索。本阶段不启动 Company HTTP 服务，不执行评测 SDK，不实现 React 或完整 OTel 观察系统。

此前《Observe架构设计》的 Company HTTP Driver、服务端口和健康检查路线暂时后置；当前采用容器内直接调用 Graph。Registry、Runtime、Adapter、Interceptor 的现有职责和代码继续复用，不另建 Driver 工厂、模型代理或第二套评测循环。

## 一、目标链路与边界

```text
注册表选中 Agent + 一次原生输入
    → 现有 RuntimeFactory / ContainerAgentAdapter
    → 一次性执行策略准备输入和输出位置
    → 现有 DockerRuntime / DockerSession
    → 容器内通用 worker
    → 现有 AdapterFactory
    → 现有 LangGraphAdapter / loader
    → Company 原生 Graph
       ├→ 原 OpenAI/Gemini 客户端 → 现有 Interceptor → OpenRouter
       └→ 原 Tavily 客户端 → Tavily
    → AdapterInvocation / 失败信息
    → 宿主机取得结果、清理资源
```

宿主机不导入 Agent 源码；容器 worker 直接调用 AdapterFactory，不能再次经过 RuntimeFactory 的 Docker 分支。`adapter.mode=in_process` 在这条路径里描述容器内部的调用方式。

本阶段一次输入对应一次进程执行，不承诺跨调用内存会话。不把这个模式自动套到所有 Docker Agent，更不能在未来多轮 SDK 测试中静默重启 Agent。已有显式 container_caller 仍可用于原生服务调用。一次性 worker 策略通过外层配置明确选择，缺失 caller/策略的 Agent 继续报错。

## 二、动手前的基线记录

1. 记录当前 Git diff、Company 上游 revision 和目录布局，不重置已有更改，不恢复删除的 Agent。
2. 执行与本轮相关的现有离线测试，区分已有失败与新增回归；记录 Python/依赖版本。不能把依赖缺失或跳过等同通过。
3. 容器测试前检查 Docker 引擎；上次引擎不可连接，不能据此声称本次也不可用，实施时重新验证。
4. 测试只检查凭据是否配置，不打印内容。第一、二步不发起真实模型/搜索请求。

## 三、第一步：修复 Adapter 在 Docker 路径缺席

### 改动

复用并按需修改：

- `agentbench/adapter/factory.py`
- `agentbench/adapter/langgraph/config.py`
- `agentbench/adapter/langgraph/loader.py`
- `agentbench/adapter/langgraph/adapter.py`
- `agentbench/runtime/factory.py`
- `agentbench/runtime/agentcontainer/adapter.py`

新增的核心代码仅为容器内共用 worker，以及 worker 结果的读写帮助函数，放在现有 `runtime/agentcontainer/` 下。它负责启动一次调用，不负责 SDK、模型重定向或业务搜索。

1. 先验证 Company 已有 `langgraph.json → langgraph_entry.py:graph`。其代码是 `Graph().compile()`，不能因为存在标准入口就假定与 `Graph(company=...).run(thread)` 等价。
2. 核对原 Graph 初始化的 messages/company/job_id 等字段，以及输出 report 是否受编译图 schema 过滤。用独立真实 StateGraph 样本复现同类输入/输出形状，再决定最小改动。
3. 优先使用现有 Adapter。如果必须按原 Graph.run 读取流式节点更新，在 LangGraph Adapter 增加明确选择的执行/输出策略；不让所有图默认切流，也不遍历任意嵌套字段猜报告。
4. 仅 Company 特有的构造/初始化保留在外层薄绑定。原 `agent/` 不改；若需要外层入口，显式声明来源根并分别校验路径，不以放松 `../` 校验实现。
5. worker 读取原生结构化输入并调用 `adapter.ainvoke(input, run_config=...)`；callbacks/thread 配置原样传递。close 放在 finally，成功写完整结果，失败返回错误类型、阶段及非零退出码。
6. 宿主机一次性策略接回现有 ContainerAgentAdapter。该策略的 load 只准备配置/执行条件，输入到达后才启动工作进程；原有原生 caller 路径的生命周期保持兼容。不要为了等输入引入常驻 HTTP 服务或 stdin 响应解析。

### 测试设计

扩展现有 `test_adapter_factory.py / test_langgraph_adapter.py / test_container_runtime.py`，新增 `test_container_worker.py`。

| 用例 | 如何验证 | 要抓住的错误 |
|---|---|---|
| 标准 LangGraph 执行 | 独立两节点 StateGraph，输入变换后生成可计算结果 | 只创建 Adapter 却未执行 Graph |
| Docker 路由归属 | 宿主机导入守卫 + 子进程实际执行样本 | 宿主机提前导入 Agent、容器内再次调用 Docker |
| 异步图 | 图只有异步节点，worker 实际完成 ainvoke | 错用 invoke 或 asyncio.run 嵌套 |
| 输入完整性 | company、company_url、industry、hq_location 字段原样到达样本节点 | 丢字段、把字典转字符串或把任意任务文本冒充公司名 |
| Company 形状样本 | 初始化默认消息 + 节点更新里 report，验证明确策略 | 改入口后漏初始状态或取不到报告 |
| 回调与 thread | 真 callback 收到节点开始/结束，同一配置 ID 到达图 | run_config 在跨边界过程中丢失；这不是完整 OTel 验证 |
| 失败路径 | 缺入口、节点抛错、缺预期输出 | 返回空结果却退出 0；错误阶段不明确 |
| 路径和导入隔离 | 现有 root/src、路径越界测试，另加重复模块名的独立进程样本 | 导错其他 Agent 或意外执行外层任意文件 |
| SDK 独立 | 无 Defuze SDK 的测试环境，运行 worker 样本 | worker 意外导入/初始化评测 SDK |
| 原 caller 兼容 | 保留现有显式 caller 调用及关闭行为测试 | 新 worker 模式破坏原生调用扩展点 |

使用独立测试目录和临时 Agent 单元，不依赖真实 API，不恢复旧删除样本。mock 仅隔离外部网络/进程边界；关键执行测试要运行真实 Adapter 和样本图，不能全链路 mock 后只断言调用次数。

### 验收与停点

离线子进程完成“输入 → worker → 实际 LangGraphAdapter → 实际样本图 → 结果”，失败稳定非零退出，回调及配置未丢失，现有适配/路径测试无新增回归。交付 Company 入口是否可直接复用的证据和必要薄绑定说明；此时尚不宣称 Docker 或真实业务成功。

## 四、第二步：补齐 Docker 配置和任务交付

### 改动

主要修改：

- `resources/agents/01-company-research-agent/{agent.toml,Dockerfile,.dockerignore}`
- `agentbench/runtime/agentcontainer/config.py`
- `agentbench/runtime/docker/{runtime.py,session.py,image_builder.py}`（后者仅在构建输入覆盖不足时修改）
- `pyproject.toml` 的运行包构建/安装配置（确有必要时）

1. 补 `[launch]` 和显式 worker 执行模式。镜像保留外层单元/agent 子目录关系，让现有 config/loader 得到正确 source_root。
2. 从本地构建 wheel 安装需要的 ABB 执行代码，使用受控 wheel/context 挂载或构建输入。镜像内不要求评测 SDK，依赖不通过复制宿主机 venv 交付。
3. 在现有 DockerRuntime 增加可选的每次调用上下文：只读输入文件挂载、可写结果目录、调用 ID。启动命令使用 argv，避免公司名或 JSON 内容拼 shell 命令。
4. worker 启动前输入文件已原子写好；输出用独立调用目录和原子完成文件。宿主机等待进程退出并校验调用 ID、退出码和结果文件一致性，不读取上次结果。
5. 成功内容映射回 AdapterInvocation；失败统一通过现有调用错误边界抛出。只保存普通日志作诊断，不把 stdout 当业务返回。
6. 保留非 root、只读根、tmpfs、临时 CA/模型凭据及既有 Interceptor 网络结构。只开放本次需要的结果/临时工作路径。
7. 先核对直接 Graph 路径实际写盘需求。此前 HTTP application 导入时创建 pdfs 的要求不自动套用到新路径。
8. 本轮独立补齐一次调用的超时与停止行为；配置 timeout_sec 不能继续只有解析没有执行。退出后保留结果，清理只针对当前调用创建的资源。

内部输入/结果文件仅用于 ABB worker 的一次性交付，不新增 Agent 必须实现的通信格式，也不改变未来原生 CLI/HTTP 接入方式。

### 测试设计

扩展 `test_container_runtime.py / test_docker_runtime.py`；增加明确标记的 Docker 集成测试。

| 用例 | 检查点 |
|---|---|
| 配置校验 | 缺 launch、无效 argv、越界挂载、无效 timeout 在启动前报错 |
| 镜像布局 | 镜像中真实运行 loader，找到 manifest、原 source_root 和依赖 |
| 输入交付 | 中文、空格、换行、引号等输入原样到达，不经过 shell 解释 |
| 成功执行 | 真实容器运行离线图，非 root/只读根配置下取得结果和退出 0 |
| 失败执行 | 节点抛错、异常进程退出、无结果文件、损坏结果文件分别报错 |
| 结果归属 | 两个不同调用目录，不接受旧 ID 或上次成功文件 |
| 超时/取消 | 阻塞样本超时后结束容器、保留诊断；Ctrl+C 不遗留当前资源 |
| 资源隔离 | 输入不可写、结果可写、源码与根不可写；不扩大现有权限 |
| 构建覆盖 | 修改 worker wheel/绑定/manifest 后不能误用不含改动的旧镜像 |
| 凭据边界 | 构建上下文没有 .env/密钥，日志与结果不泄漏测试用凭据 |

Docker 不可用时离线单测照常进行，Docker 集成项报告“未执行”，不能以 mock Docker 测试代替验收。Company 镜像需要实际构建；没有凭据时可验证 imports/准备路径，不伪造 Company 已执行。

### 验收与停点

镜像实际构建、容器离线样本真实执行成功；Company 代码与依赖可导入，运行配置正确；失败、超时、清理经过容器验证。报告构建命令、镜像 ID、退出码及结果路径。此阶段不发起 Company 研究。

## 五、第三步：模型拦截和真实搜索

### 3A. 先复用 OpenAI 路径

沿用现有 protocol/auth/target 注册机制、CA 信任、临时凭据与 OpenRouterProvider，配置 Company 原客户端的真实 host/path/env。不要改成客户端直连 OpenRouter。

测试：原 OpenAI 客户端发请求，经真实拦截链路到受控上游测试服务，验证 source/target model、认证替换和响应可读；保留原有 OpenAI/Responses/Anthropic 回归用例。测试网络 fixture 不改变生产路由。

### 3B. Gemini 双向兼容

先在 Company 固定依赖版本中确认 Google 客户端的实际 HTTP/gRPC 传输、endpoint、认证位置、streaming 和 generation 参数，不能凭类名假定 wire format。

在现有 `services/model-interceptor/src/defuzex_model_interceptor/` 的 auth、targets、protocols、addon、registry 中扩展能力。当前 ProtocolPlugin 主要做记录解码、TargetProviderPlugin 做请求准备，尚无通用响应回译钩子；需增加可选 codec 能力，已有协议默认透传响应，保持兼容。

实现范围先满足 Company 实际请求：输入消息/系统提示、生成配置、普通文本响应、流式内容、finish reason、usage 和错误。客户端可能提交但尚不支持的选项必须明确拒绝，不声称兼容完整 Gemini API。若实际使用 gRPC，先解决当前代理的传输支持问题，再承诺端到端可执行。

| 测试 | 核心断言 |
|---|---|
| 请求转换 | Company 实际请求样本在转换后保留必要语义，不只检查 JSON 有效 |
| 普通响应回译 | 原 Google 客户端真实解析成功，取得文本与结束状态 |
| 流式回译 | 任意 TCP 分片边界、Unicode 分片、多事件合并、结束事件均正确解析 |
| 参数与错误 | 不支持项、限流、上游失败、格式错误明确返回；失败不变成空成功 |
| 凭据 | 临时凭据无效时在转发前拒绝；原认证字段移除，OpenRouter Key 不回流 Agent |
| 老插件兼容 | 既有协议仍正确工作，未配置 codec 时不改变响应体 |
| Interceptor 留档 | 原请求与转发后请求可区分；call_id 关联响应；截断明确标记 |

### 3C. Tavily 真实搜索

配置 `TAVILY_API_KEY` 的 secret 注入和真实网络路径，保留原 search/extract/crawl 方法。没有 Key 明确报业务配置缺失；生产路径不返回 Wangyi 的固定 OpenAI 资料。

先用受控测试响应验证凭据、超时和错误传递，再用配置好的真实 Tavily 验证调用；不对搜索结果正文或实时排名做固定断言。原 Agent 本身可能降级处理搜索失败，应保留原行为并明确记录，而不是改变为另一套业务策略。

### 第三步验收

1. OpenAI、Google 原客户端分别通过现有 Interceptor 和所配置 OpenRouter 模型完成最小调用；记录源协议、目标路由、返回解析结果。
2. 真实 Tavily 搜索可执行，缺 Key/错误响应可诊断。
3. 原 Company 流程执行一次指定公司输入，取得非空报告，至少验证各实际模型路径没有绕过 Interceptor；结果记录模型、source revision、镜像、运行参数与调用证据。
4. 不要求两次研究报告逐字相同，也不把出口连通/报告非空当成研究正确性的完整评价。
5. 只有所有必需路径验证通过才称“真实 Company 执行接通”。某条协议未实现、真实测试缺凭据或服务不可达，明确列为未完成，不能用离线 fixture 冒充。

此阶段可得到现有 Interceptor 的模型请求/响应记录，不等于完整节点/工具 OTel trace。OTel、observe 和 React 在后续阶段接这条链路。

## 六、测试组织和执行顺序

```text
现有相关测试基线
    → 第一步离线单测 + 子进程集成
    → 第二步离线回归 + 真实 Docker 集成
    → 第三步协议 fixture + 原客户端集成
    → OpenRouter/Tavily 最小真实调用
    → 一次真实 Company 研究
    → 受影响模块回归 + 本轮验收报告
```

测试分 `unit / docker / live`，普通 pytest 不隐式调用真实模型或搜索。live 显式选择、配置超时和可控制的调用规模，失败不无限重试。Docker 构建可能下载依赖，但不代表业务 API 测试。复用 pytest 和现有 fixtures，不额外引入测试框架。

每步报告四项：改了什么、哪些检查真正执行并通过、哪些失败/跳过及原因、下一步剩余事项。没有新改动或未解决风险，不重复跑已通过的昂贵检查。

## 七、文档和范围收束

- 实施时更新 Runtime、Layout/Reference 与相关入口文档；当前 Factory 文档“所有搜索必须 mock”的条款与用户明确要求冲突，应注明真实观察路径使用真实搜索，不以旧条款阻止当前授权范围。
- 目前不删除现有 Adapter，不新建并行 Registry、Docker runner 或模型代理服务。
- 不修改《用户的想法》，不把三步成功写成 SDK 评测、完整 trace 或网页已完成。
- 第一阶段从最小独立样本证明执行链，再推进 Company；不会先安装一套大而全观察平台。
