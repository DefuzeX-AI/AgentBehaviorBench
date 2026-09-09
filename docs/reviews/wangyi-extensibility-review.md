# Wangyi 全量适配器巡检与 ABB 扩展建议

日期：2026-09-08。目标：判断除 Company Research 外的 Agent 如何接入行为观察台。

## 范围与证据等级

- 本地实际目录为 `C:/Song_startup/benchmark/wangyi/agents`。
- 遍历全部 176 个编号目录（001–176 无重复、无缺号）：tested 20、untested 156。
- 读取现有 agent.md、runtime/meta.json、entrypoint.py、run.sh、README、Dockerfile，共 975 个文件；解析全部 175 个入口文件的函数与调用；025 只有需求说明，没有 runtime。
- 此目录主要是接入层与运行留档，不能据此声称已阅读 176 个完整上游源码或验证所有原生接口。
- 另外读取 STATUS.tsv 全部 176 行、156 份本地冒烟结果；没有执行上游代码、启动容器、调用模型或修改 Wangyi。
- `tested` 是目录归类，`verify_level` 是 metadata 字段，状态表档位是另一套留档统计；三者不混用。以下分类描述现有驱动代码，不是原项目接口的市场占比。

## 全量扫描结果

| 现有驱动实现 | 数量 | 意义 |
| --- | ---: | --- |
| 通用图加载 | 66 | 通过 _load_graph 与 _ainvoke 加载并执行图 |
| 通用命令行驱动 | 82 | 探测命令帮助，选择参数，启动子进程 |
| 专用驱动 | 27 | 24 个专用 Python 驱动、3 个专用 subprocess 驱动 |
| 无适配器 | 1 | 025 Azure Chat with Your Data |

metadata.kind 的分布却是 cli 138、langgraph 36、in-process 1、缺失 1，证明不能只按该字段判断接入方式。
175 份 metadata 中 ports 全为空、health 全为 null。这只能说明这些声明没有提供 HTTP 就绪与访问契约，不能推论原项目没有后端。

本地 STATUS.tsv 的档位分布：A 18、B 4、C 80、D 64、X 9、E 1。其口径见 Wangyi 的 STATUS.md，未重新执行认证。其中 A 表示有正式 case 的成功运行、输出与 trace 留档；D 表示未真正跑起业务或只验证启动。仅按 metadata 的 invoked 101 个计算成功覆盖会失真。
另有 156 份冒烟结果，111 份标记 ok=true、45 份不是 true；ok=true 不证明执行了正确的业务入口、调用了模型或完成了生产流程。

## 有代表性的实际调用

| Agent | 本地驱动做什么 | 对 ABB 的启示 |
| --- | --- | --- |
| 015 Company Research | 直接 Graph(...).run(thread)，并替换模型/搜索客户端 | 当前 ABB 应调用原 HTTP 后端；Wangyi 的 cli 标签不代表原生 CLI |
| 003 GPT Researcher | GPTResearcher → conduct_research → write_report；run.sh 准备 Ollama 嵌入服务 | 支持 Python 多阶段调用与依赖服务 |
| 020 Waku | Waku(Settings()).respond(message)，之后 close | 不经过 LangGraph 的 Python API 也能是 Agent 入口 |
| 039 react-agent | graph.ainvoke + callbacks | 框架图调用是一种驱动能力，不是所有 Agent 的统一入口 |
| 016 RA.Aid | subprocess 执行 python -m ra_aid --message ... | 保留原 CLI；参数构造与结果读取属于该驱动 |
| 018 DATAGEN | 准备 CSV，执行工作流，读取报告文件 | 输入/输出可能含文件与产物，不只是聊天文本 |
| 029 WebRover | setup_browser → Chrome/CDP → task_agent.ainvoke | 浏览器是运行依赖；只有需要操作 UI 的任务才用浏览器交互驱动 |
| 082 RAG Customer Support | Qdrant sidecar + 图调用 | 容器内 Agent 之外还可能有依赖服务与状态 |
| 105 WhatsApp Agent | 加载图工厂；通用 _ainvoke 处理异步上下文 | 图内核调用不能替代 WhatsApp 端到端交互验证；资源生命周期要保持 |
| 025 Azure Chat with Your Data | 只有需求说明 | 不应把声明存在算作已经可运行 |

## 不应照搬的做法

1. **自动找到可执行文件便认定为 Agent 入口。** 043 指向 utils/db_utils.py，088 指向生成 manifest 的脚本，162 指向 scaffold_mart.py，163 指向 data/sync_files2.py；这些是需要人工业务验证的候选，不是已确认的研究/问答接口。若只看 --help 或输出非空，容易把辅助脚本算成 Agent 成功运行。
2. **自动猜输入语义。** 通用图驱动会尝试 messages、payload.state，或选择第一个必填字符串字段。可用于生成草稿，不能在正式观察时静默把公司名塞进别的字段。
3. **把框架与通信方式混为一个 kind。** 一个 LangGraph 项目同时可能提供 HTTP、CLI 和 Python 入口。观察任务应明确走哪条路径。
4. **把适配后的行为当成原生行为。** Company 驱动替换 Tavily，公共 sitecustomize 还可能替换搜索、嵌入或重排逻辑。应显式记录所启用替换，区分真实调用和测试替身。
5. **把跨进程日志合并当成完整 trace。** 通用 CLI 驱动的 _child_spans 会为缺失的 trace_id/span_id 补值，并保留 parent_span_id=None；代码注明子进程没有父进程上下文。它适合保留观测片段，不足以证明完整因果树。
6. **复制一整份适配器。** 共享框架采集与生命周期应集中维护；每个 Agent 只保留本项目的启动声明、原生 API 映射和确有必要的专用代码。

## 建议的扩展边界

```text
ABB React 页面 / 调试客户端
→ ABB 自己的 HTTP API
→ ObservationSession（环境/容器存活的一段会话）
   ├─ Runtime：启动、服务依赖、就绪、清理
   ├─ Driver：原生 HTTP / Python 调用 / 命令 / 必要的交互
   └─ Observer：OTel 框架插桩、模型拦截、工具与产物采集
→ 每次任务单独建立 run，关联原 job/thread ID
```

网页都调用 ABB 的 API；ABB 内部依据 Agent 的原生接口选择驱动。统一的是 ABB 的调度和观察入口，不能要求上游 Agent 都提供 HTTP、invoke 方法或固定文本输出。

这三个维度要独立：

- Runtime 回答“进程怎么启动、依赖什么服务、何时就绪、什么时候销毁”。
- Driver 回答“如何提交这项任务、如何取得结果/产物、怎样继续会话”。
- Observer 回答“能采到 HTTP 边界、图节点、模型、工具或浏览器中的哪些事件”。

只安装 LangGraph observer 不会自动解决 HTTP job 的轮询，只有 HTTP driver 也看不到图内部的节点。Docker exec 捕获的 stdout 更不能自动等同于完整 Agent 行为。

## 配置与少量代码的分工

通用字段放外层 agent.toml：启动 argv/workdir、端口/就绪检查、依赖服务、环境变量名、驱动选择、输入/产物描述、观测选择。复杂认证、任务流转或多阶段 Python 调用可以放外层专用 driver.py。不要为了配置一切而发明复杂的 TOML 脚本语言，也不要修改 agent/ 中的上游业务源码。

同一 Agent 可声明多种入口，但一次 run 必须记录实际入口。例如 Company 的 HTTP 调用观察到后端任务管理；直接调用 Graph.run 观察到图内核。二者可能产出相同报告，但验证的行为范围不同。

驱动按能力声明：submit、stream、cancel、resume、reset、artifacts 等都不是强制项。页面只显示实际实现的操作；HTTP 断开不代表后台任务已取消。对尚不能自动驱动的 Agent，允许手动从原生客户端触发并只开启观察，记录其覆盖范围。

任务生命周期与容器生命周期分开。常驻服务可能处理多次任务；CLI 可能每项任务一个进程；有状态的图、MCP 会话、数据库需要复用或显式 reset。任务要支持 pending/running/waiting/completed/failed/cancelled 等真实状态，不强迫所有任务一次输入立即结束。

跨进程采集使用真实上下文传递。任务入口关联 observation run_id、原 job_id、trace_id；HTTP 或子进程边界传播父上下文，异步分支和重试保留关系。缺少插桩时明确标记只看到外部请求/日志，不编造缺失节点。模型转发继续用 ABB 的可信 Interceptor，采集与模型改写分别记录。

## 建议先做的最小范围

1. 只接现有 Company：启动原后端，HTTP 提交 /research，消费其 SSE/报告接口，关联 job_id，处理失败和关闭。
2. 将这段业务映射放入 Company driver；ObservationSession 不出现 Company、/research 等专属判断。框架采集代码独立于该 driver。
3. 使用独立离线测试样本验证 Python 方法和命令入口，检验核心是否与 HTTP 解耦；不增加真实注册 Agent 或下载其他项目。
4. 再按实际需求补浏览器、依赖服务、交互与恢复能力。每次都用任务真的执行、trace 关联正确、产物能读取作为验收。

## 逐 Agent 清单

下表的“档位”来自本地 STATUS.tsv，“metadata 状态”来自 meta.json；只报告现存声明/留档。点击证据可直接看调用实现。

| ID | 项目 | 分组 | 驱动代码分类 | 入口记录 | metadata 状态 | 档位 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 001 | TauricResearch__TradingAgents | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/001_TauricResearch__TradingAgents/runtime/entrypoint.py) |
| 002 | bytedance__deer-flow | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/002_bytedance__deer-flow/runtime/entrypoint.py) |
| 003 | assafelovic__gpt-researcher | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/003_assafelovic__gpt-researcher/runtime/entrypoint.py) |
| 004 | langchain-ai__deepagents | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/004_langchain-ai__deepagents/runtime/entrypoint.py) |
| 005 | langchain-ai__open-swe | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/005_langchain-ai__open-swe/runtime/entrypoint.py) |
| 006 | xerrors__Yuxi | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/006_xerrors__Yuxi/runtime/entrypoint.py) |
| 007 | PurpleAILAB__Decepticon | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/007_PurpleAILAB__Decepticon/runtime/entrypoint.py) |
| 008 | EvoScientist__EvoScientist | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/008_EvoScientist__EvoScientist/runtime/entrypoint.py) |
| 009 | JoshuaC215__agent-service-toolkit | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | B case 有产出未跑完 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/009_JoshuaC215__agent-service-toolkit/runtime/entrypoint.py) |
| 010 | Awarexone__Agentic-Bug-Hunter | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/010_Awarexone__Agentic-Bug-Hunter/runtime/entrypoint.py) |
| 011 | simonlin1212__TradingAgents-astock | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/011_simonlin1212__TradingAgents-astock/runtime/entrypoint.py) |
| 012 | wassim249__fastapi-langgraph-agent-production-ready-template | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/012_wassim249__fastapi-langgraph-agent-production-ready-template/runtime/entrypoint.py) |
| 013 | beenuar__AiSOC | tested | 专用子进程驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/013_beenuar__AiSOC/runtime/entrypoint.py) |
| 014 | 1517005260__graph-rag-agent | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/014_1517005260__graph-rag-agent/runtime/entrypoint.py) |
| 015 | guy-hartstein__company-research-agent | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/015_guy-hartstein__company-research-agent/runtime/entrypoint.py) |
| 016 | ai-christianson__RA.Aid | tested | 专用子进程驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/016_ai-christianson__RA.Aid/runtime/entrypoint.py) |
| 017 | olaxbt__ai-market-maker | tested | 专用子进程驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/017_olaxbt__ai-market-maker/runtime/entrypoint.py) |
| 018 | zi-yue-1129__DATAGEN | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/018_zi-yue-1129__DATAGEN/runtime/entrypoint.py) |
| 019 | ginlix-ai__LangAlpha | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/019_ginlix-ai__LangAlpha/runtime/entrypoint.py) |
| 020 | ShenSeanChen__waku-agent | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/020_ShenSeanChen__waku-agent/runtime/entrypoint.py) |
| 021 | rotemweiss57__gpt-newspaper | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | B case 有产出未跑完 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/021_rotemweiss57__gpt-newspaper/runtime/entrypoint.py) |
| 022 | darwin-lau__langmanus | untested | 通用图加载 | langgraph:/app/src/graph/builder.py:build_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/022_darwin-lau__langmanus/runtime/entrypoint.py) |
| 023 | rcortx__kiwiq | untested | 通用命令行驱动 | cli:/app/untrusted_code_runner/runner.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/023_rcortx__kiwiq/runtime/entrypoint.py) |
| 024 | SalesforceAIResearch__enterprise-deep-research | untested | 通用图加载 | ./src/graph.py:graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/024_SalesforceAIResearch__enterprise-deep-research/runtime/entrypoint.py) |
| 025 | Azure-Samples__chat-with-your-data-solution-accelerator | untested | 无适配器 | 只有 agent.md | — | E 未适配 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/025_Azure-Samples__chat-with-your-data-solution-accelerator/agent.md) |
| 026 | test-zeus-ai__testzeus-hercules | untested | 通用命令行驱动 | testzeus-hercules | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/026_test-zeus-ai__testzeus-hercules/runtime/entrypoint.py) |
| 027 | EuniAI__Prometheus | untested | 通用命令行驱动 | cli:/app/prometheus/script/github_issue_debug.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/027_EuniAI__Prometheus/runtime/entrypoint.py) |
| 028 | Fullive-AI__Anima | untested | 通用命令行驱动 | anima | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/028_Fullive-AI__Anima/runtime/entrypoint.py) |
| 029 | hrithikkoduri__WebRover | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/029_hrithikkoduri__WebRover/runtime/entrypoint.py) |
| 030 | mikekelly__AgentK | untested | 通用图加载 | langgraph:/app/agents/hermes.py:graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/030_mikekelly__AgentK/runtime/entrypoint.py) |
| 031 | FareedKhan-dev__production-grade-agentic-system | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/031_FareedKhan-dev__production-grade-agentic-system/runtime/entrypoint.py) |
| 032 | XD-MHLOO__Osintgraph | untested | 通用命令行驱动 | osintgraph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/032_XD-MHLOO__Osintgraph/runtime/entrypoint.py) |
| 033 | zamalali__DeepGit | untested | 通用命令行驱动 | deepgit | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/033_zamalali__DeepGit/runtime/entrypoint.py) |
| 034 | Pan-Chera__Multi-Agent-CAD | untested | 通用图加载 | multi_agent_cad/graph.py:build_graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/034_Pan-Chera__Multi-Agent-CAD/runtime/entrypoint.py) |
| 035 | lc2panda__alphastream | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/035_lc2panda__alphastream/runtime/entrypoint.py) |
| 036 | cuga-project__cuga-agent | untested | 通用命令行驱动 | cuga | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/036_cuga-project__cuga-agent/runtime/entrypoint.py) |
| 037 | NVIDIA-AI-Blueprints__aiq | untested | 通用命令行驱动 | cli:/app/frontends/cli/cli.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/037_NVIDIA-AI-Blueprints__aiq/runtime/entrypoint.py) |
| 038 | icey1287__SuperMew | untested | 通用命令行驱动 | supermew-registry | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/038_icey1287__SuperMew/runtime/entrypoint.py) |
| 039 | langchain-ai__react-agent | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/039_langchain-ai__react-agent/runtime/entrypoint.py) |
| 040 | nirbar1985__ai-travel-agent | untested | 通用命令行驱动 | cli:/app/app.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/040_nirbar1985__ai-travel-agent/runtime/entrypoint.py) |
| 041 | vinay-gatech__stocks-insights-ai-agent | tested | 通用图加载 | rag_graphs/news_rag_graph/graph/graph.py:app（扫源码找到，非 langgraph.json） | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/041_vinay-gatech__stocks-insights-ai-agent/runtime/entrypoint.py) |
| 042 | Chen-zexi__open-ptc-agent | untested | 通用图加载 | libs/ptc-agent/ptc_agent/agent/graph.py:agent | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/042_Chen-zexi__open-ptc-agent/runtime/entrypoint.py) |
| 043 | isoftstone-data-intelligence-ai__efflux-backend | untested | 通用命令行驱动 | cli:/app/utils/db_utils.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/043_isoftstone-data-intelligence-ai__efflux-backend/runtime/entrypoint.py) |
| 044 | braincrew-lab__langgraph-mcp-agents | untested | 通用命令行驱动 | cli:/app/mcp_server_rag.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/044_braincrew-lab__langgraph-mcp-agents/runtime/entrypoint.py) |
| 045 | stophobia__deerflow2.0-enhanced | untested | 通用图加载 | langgraph:/app/backend/deerflow/agents.py:make_lead_agent | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/045_stophobia__deerflow2.0-enhanced/runtime/entrypoint.py) |
| 046 | Westlake-AGI-Lab__AppAgentX | untested | 通用图加载 | langgraph:/app/deployment.py:build_workflow | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/046_Westlake-AGI-Lab__AppAgentX/runtime/entrypoint.py) |
| 047 | nuglifeleoji__Options-Analytics-Agent | untested | 通用图加载 | Week1/first_simple_openai_agent.py:graph（扫源码找到，非 langgraph.json） | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/047_nuglifeleoji__Options-Analytics-Agent/runtime/entrypoint.py) |
| 048 | langtalks__swe-agent | untested | 通用图加载 | ./agent/graph.py:swe_agent | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/048_langtalks__swe-agent/runtime/entrypoint.py) |
| 049 | tablegpt__tablegpt-agent | untested | 通用命令行驱动 | cli:/app/realtabbench/agent_eval/__main__.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/049_tablegpt__tablegpt-agent/runtime/entrypoint.py) |
| 050 | zhongyu09__openchatbi | untested | 通用图加载 | langgraph:/app/openchatbi/__init__.py:get_default_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/050_zhongyu09__openchatbi/runtime/entrypoint.py) |
| 051 | 51bitquant__ai-hedge-fund-crypto | untested | 通用命令行驱动 | cli:/app/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/051_51bitquant__ai-hedge-fund-crypto/runtime/entrypoint.py) |
| 052 | wassim249__YT-Navigator | untested | 通用图加载 | langgraph:/app/app/services/agent/main_graph.py:get_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/052_wassim249__YT-Navigator/runtime/entrypoint.py) |
| 053 | esxr__langgraph-mcp | untested | 通用图加载 | ./src/langgraph_mcp/build_router_graph.py:graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/053_esxr__langgraph-mcp/runtime/entrypoint.py) |
| 054 | NicholasGoh__fastapi-mcp-langgraph-template | untested | 通用命令行驱动 | cli:/app/backend/mcp/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/054_NicholasGoh__fastapi-mcp-langgraph-template/runtime/entrypoint.py) |
| 055 | psyray__oasis | untested | 通用命令行驱动 | oasis | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/055_psyray__oasis/runtime/entrypoint.py) |
| 056 | bcefghj__multi-agent-ecommerce-system | untested | 通用图加载 | langgraph:/app/python/orchestrator/graph.py:build_recommendation_graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/056_bcefghj__multi-agent-ecommerce-system/runtime/entrypoint.py) |
| 057 | vibesurf-ai__VibeSurf | untested | 通用命令行驱动 | vibesurf | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/057_vibesurf-ai__VibeSurf/runtime/entrypoint.py) |
| 058 | NanGePlus__LangGraphChatBot | untested | 通用命令行驱动 | cli:/app/01_ChatBot/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/058_NanGePlus__LangGraphChatBot/runtime/entrypoint.py) |
| 059 | SponsioLabs__Sponsio | untested | 通用命令行驱动 | sponsio | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/059_SponsioLabs__Sponsio/runtime/entrypoint.py) |
| 060 | Tswoen__Paper-Agent | untested | 通用图加载 | langgraph:/app/src/graph/graph.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/060_Tswoen__Paper-Agent/runtime/entrypoint.py) |
| 061 | brainqub3__jar3d_meta_expert | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/061_brainqub3__jar3d_meta_expert/runtime/entrypoint.py) |
| 062 | john-adeojo__graph_websearch_agent | tested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/062_john-adeojo__graph_websearch_agent/runtime/entrypoint.py) |
| 063 | Arvo-AI__aurora | untested | 通用命令行驱动 | cli:/app/kubectl-agent/src/agent.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/063_Arvo-AI__aurora/runtime/entrypoint.py) |
| 064 | skygazer42__GustoBot | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/064_skygazer42__GustoBot/runtime/entrypoint.py) |
| 065 | togethercomputer__open_deep_research | untested | 通用命令行驱动 | cli:/app/src/together_open_deep_research.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/065_togethercomputer__open_deep_research/runtime/entrypoint.py) |
| 066 | Xeron2000__openOii | untested | 通用图加载 | langgraph:/app/backend/app/orchestration/graph.py:build_phase2_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/066_Xeron2000__openOii/runtime/entrypoint.py) |
| 067 | amanv1906__GENAI-CareerAssistant-Multiagent | untested | 通用图加载 | langgraph:/app/agents.py:define_graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/067_amanv1906__GENAI-CareerAssistant-Multiagent/runtime/entrypoint.py) |
| 068 | kaymen99__sales-outreach-automation-langgraph | untested | 通用命令行驱动 | cli:/app/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/068_kaymen99__sales-outreach-automation-langgraph/runtime/entrypoint.py) |
| 069 | bcefghj__smart-cs-multi-agent | untested | 通用图加载 | langgraph:/app/python-impl/agents/supervisor.py:create_supervisor_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/069_bcefghj__smart-cs-multi-agent/runtime/entrypoint.py) |
| 070 | NVlabs__SpatialClaw | untested | 通用命令行驱动 | cli:/app/spatial_agent/gpu_dashboard/__main__.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/070_NVlabs__SpatialClaw/runtime/entrypoint.py) |
| 071 | cnunescoelho__kiroku | untested | 通用命令行驱动 | cli:/app/kiroku_app.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/071_cnunescoelho__kiroku/runtime/entrypoint.py) |
| 072 | NVIDIA-AI-IOT__remembr | untested | 通用命令行驱动 | cli:/app/remembr/agents/remembr_agent.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/072_NVIDIA-AI-IOT__remembr/runtime/entrypoint.py) |
| 073 | CronusL-1141__AI-company | untested | 通用命令行驱动 | aiteam | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/073_CronusL-1141__AI-company/runtime/entrypoint.py) |
| 074 | EthanXiang777__circuit-framework | untested | 通用命令行驱动 | tradingagents | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/074_EthanXiang777__circuit-framework/runtime/entrypoint.py) |
| 075 | GoogleCloudPlatform__cymbal-air-toolbox-demo | untested | 通用命令行驱动 | 专用 run_agent；见实现 | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/075_GoogleCloudPlatform__cymbal-air-toolbox-demo/runtime/entrypoint.py) |
| 076 | ivebotunac__PrimoAgent | untested | 通用图加载 | langgraph:/app/src/workflows/workflow.py:create_workflow | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/076_ivebotunac__PrimoAgent/runtime/entrypoint.py) |
| 077 | Negai-ai__AgentClaw | untested | 通用命令行驱动 | agentclaw | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/077_Negai-ai__AgentClaw/runtime/entrypoint.py) |
| 078 | lhh737__LangChain-ReAct-Agent | untested | 通用命令行驱动 | cli:/app/rag/rag_service.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/078_lhh737__LangChain-ReAct-Agent/runtime/entrypoint.py) |
| 079 | didilili__shopkeeper-agent | untested | 通用图加载 | app/agent/graph.py:graph（扫源码找到，非 langgraph.json） | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/079_didilili__shopkeeper-agent/runtime/entrypoint.py) |
| 080 | kmeanskaran__stock-agent-ops | untested | 通用图加载 | langgraph:/app/src/agents/graph.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/080_kmeanskaran__stock-agent-ops/runtime/entrypoint.py) |
| 081 | jd-opensource__JoySafeter | untested | 通用命令行驱动 | cli:/app/backend/app/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/081_jd-opensource__JoySafeter/runtime/entrypoint.py) |
| 082 | liangdabiao__langgraph_multi-agent-rag-customer-support | tested | 通用图加载 | customer_support_chat/app/graph.py:multi_agentic_graph（扫源码找到，非 langgraph.json） | invoked | B case 有产出未跑完 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/082_liangdabiao__langgraph_multi-agent-rag-customer-support/runtime/entrypoint.py) |
| 083 | hwchase17__langchain-streamlit-template | untested | 通用图加载 | langgraph:/app/main.py:load_agent | scaffold | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/083_hwchase17__langchain-streamlit-template/runtime/entrypoint.py) |
| 084 | yolo-hyl__medical-rag | untested | 通用命令行驱动 | cli:/app/run_api.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/084_yolo-hyl__medical-rag/runtime/entrypoint.py) |
| 085 | dhruvsinghal09__Adaptive-Rag | untested | 通用图加载 | src/rag/graph_builder.py:builder（扫源码找到，非 langgraph.json） | invoked | B case 有产出未跑完 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/085_dhruvsinghal09__Adaptive-Rag/runtime/entrypoint.py) |
| 086 | HKUSTDial__DeepFund | untested | 通用命令行驱动 | cli:/app/src/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/086_HKUSTDial__DeepFund/runtime/entrypoint.py) |
| 087 | langchain-ai__new-langgraph-project | untested | 通用图加载 | ./src/agent/graph.py:graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/087_langchain-ai__new-langgraph-project/runtime/entrypoint.py) |
| 088 | goruck__home-generative-agent | untested | 通用命令行驱动 | cli:/app/scripts/gen_manifest_requirements.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/088_goruck__home-generative-agent/runtime/entrypoint.py) |
| 089 | jarrycyx__openlens-ai | untested | 通用命令行驱动 | openlens-cli | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/089_jarrycyx__openlens-ai/runtime/entrypoint.py) |
| 090 | NVIDIA-AI-Blueprints__ai-virtual-assistant | untested | 通用图加载 | src/agent/main.py:graph（扫源码找到，非 langgraph.json） | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/090_NVIDIA-AI-Blueprints__ai-virtual-assistant/runtime/entrypoint.py) |
| 091 | quarqlabs__argus | tested | 通用图加载 | agent_v1.py:app（扫源码找到，非 langgraph.json） | invoked | A 正式 case 通 | [源码](C:/Song_startup/benchmark/wangyi/agents/tested/091_quarqlabs__argus/runtime/entrypoint.py) |
| 092 | kaymen99__langgraph-email-automation | untested | 通用命令行驱动 | cli:/app/deploy_api.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/092_kaymen99__langgraph-email-automation/runtime/entrypoint.py) |
| 093 | SecurityClaw__SecurityClaw | untested | 通用图加载 | langgraph:/app/core/chat_router/logic.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/093_SecurityClaw__SecurityClaw/runtime/entrypoint.py) |
| 094 | Lyra-stellAI__BYO-LLM-WIKI | untested | 通用图加载 | langgraph:/app/skill_graph.py:get_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/094_Lyra-stellAI__BYO-LLM-WIKI/runtime/entrypoint.py) |
| 095 | artnoage__Podcast | untested | 通用命令行驱动 | cli:/app/fast_api_app.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/095_artnoage__Podcast/runtime/entrypoint.py) |
| 096 | lingxi-agent__Lingxi | untested | 通用图加载 | ./src/agent/supervisor_graph_demo.py:issue_resolve_graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/096_lingxi-agent__Lingxi/runtime/entrypoint.py) |
| 097 | mfmezger__conversational-agent-langchain | untested | 通用命令行驱动 | agent | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/097_mfmezger__conversational-agent-langchain/runtime/entrypoint.py) |
| 098 | tyxben__AI_novel | untested | 通用命令行驱动 | novel-video | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/098_tyxben__AI_novel/runtime/entrypoint.py) |
| 099 | bernatsampera__event-deep-research | untested | 通用图加载 | ./src/graph.py:graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/099_bernatsampera__event-deep-research/runtime/entrypoint.py) |
| 100 | Y-Research-SBU__PosterGen | untested | 通用图加载 | langgraph:/app/src/workflow/pipeline.py:create_workflow_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/100_Y-Research-SBU__PosterGen/runtime/entrypoint.py) |
| 101 | datawhalechina__vibe-blog | untested | 通用命令行驱动 | cli:/app/backend/app.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/101_datawhalechina__vibe-blog/runtime/entrypoint.py) |
| 102 | huygiatrng__AlpacaTradingAgent | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/102_huygiatrng__AlpacaTradingAgent/runtime/entrypoint.py) |
| 103 | KodyKendall__LlamaBot | untested | 通用图加载 | ./agents/llamabot/nodes.py:build_workflow | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/103_KodyKendall__LlamaBot/runtime/entrypoint.py) |
| 104 | billy-enrizky__openbrowser-ai | untested | 通用命令行驱动 | openbrowser-ai | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/104_billy-enrizky__openbrowser-ai/runtime/entrypoint.py) |
| 105 | lgesuellip__langgraph-whatsapp-agent | untested | 通用图加载 | ./src/agents/base/graph.py:build_agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/105_lgesuellip__langgraph-whatsapp-agent/runtime/entrypoint.py) |
| 106 | NVIDIA-AI-Blueprints__vulnerability-analysis | untested | 通用命令行驱动 | vuln-analysis | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/106_NVIDIA-AI-Blueprints__vulnerability-analysis/runtime/entrypoint.py) |
| 107 | wshobson__financial-chat | untested | 通用图加载 | langgraph:/app/app/chains/agent.py:create_anthropic_agent_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/107_wshobson__financial-chat/runtime/entrypoint.py) |
| 108 | nicoladisabato__MultiAgenticRAG | untested | 通用图加载 | main_graph/graph_builder.py:graph（扫源码找到，非 langgraph.json） | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/108_nicoladisabato__MultiAgenticRAG/runtime/entrypoint.py) |
| 109 | eosho__langchain_data_agent | untested | 通用命令行驱动 | data-agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/109_eosho__langchain_data_agent/runtime/entrypoint.py) |
| 110 | growgraph__ontocast | untested | 通用命令行驱动 | ontocast | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/110_growgraph__ontocast/runtime/entrypoint.py) |
| 111 | louisgthier__decompai | untested | 通用图加载 | src/main.py:graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/111_louisgthier__decompai/runtime/entrypoint.py) |
| 112 | Gen-Future__ExcelMind | untested | 通用命令行驱动 | excel-agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/112_Gen-Future__ExcelMind/runtime/entrypoint.py) |
| 113 | jamwithai__observable-job-agent | untested | 通用图加载 | langgraph:/app/src/job_scout/graph/graph.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/113_jamwithai__observable-job-agent/runtime/entrypoint.py) |
| 114 | Nachoeigu__agentic-customer-service-medical-clinic | untested | 通用图加载 | ./src/agent.py:app | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/114_Nachoeigu__agentic-customer-service-medical-clinic/runtime/entrypoint.py) |
| 115 | kulkarnirohit123__cra-agent | untested | 通用命令行驱动 | cra-agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/115_kulkarnirohit123__cra-agent/runtime/entrypoint.py) |
| 116 | Yanyutin753__LambChat | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/116_Yanyutin753__LambChat/runtime/entrypoint.py) |
| 117 | Yonom__assistant-ui-langgraph-fastapi | untested | 通用图加载 | backend/app/langgraph/agent.py:assistant_ui_graph（扫源码找到，非 langgraph.json） | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/117_Yonom__assistant-ui-langgraph-fastapi/runtime/entrypoint.py) |
| 118 | HezaoHezao__poirot | untested | 通用命令行驱动 | poirot | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/118_HezaoHezao__poirot/runtime/entrypoint.py) |
| 119 | fzn0x__watchtower | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/119_fzn0x__watchtower/runtime/entrypoint.py) |
| 120 | jank__curiosity | untested | 通用命令行驱动 | cli:/app/main.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/120_jank__curiosity/runtime/entrypoint.py) |
| 121 | yycyyv__M-Cube | untested | 通用命令行驱动 | cli:/app/desktop_backend_entry.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/121_yycyyv__M-Cube/runtime/entrypoint.py) |
| 122 | muratcankoylan__readwren | untested | 通用命令行驱动 | cli:/app/cli_interview.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/122_muratcankoylan__readwren/runtime/entrypoint.py) |
| 123 | guangshu100__BidMaster-Pro | untested | 通用命令行驱动 | cli:/app/start.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/123_guangshu100__BidMaster-Pro/runtime/entrypoint.py) |
| 124 | tavily-ai__meeting-prep-agent | untested | 通用命令行驱动 | cli:/app/app.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/124_tavily-ai__meeting-prep-agent/runtime/entrypoint.py) |
| 125 | ZhangJinHaHaHa__FinchainAgent | untested | 通用图加载 | main.py:app（扫源码找到，非 langgraph.json） | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/125_ZhangJinHaHaHa__FinchainAgent/runtime/entrypoint.py) |
| 126 | tevslin__meeting-reporter | untested | 通用命令行驱动 | cli:/app/mytools.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/126_tevslin__meeting-reporter/runtime/entrypoint.py) |
| 127 | ai-forever__giga_agent | untested | 通用图加载 | backend/giga_agent/agents/run.py:graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/127_ai-forever__giga_agent/runtime/entrypoint.py) |
| 128 | duartecaldascardoso__article-explainer | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/128_duartecaldascardoso__article-explainer/runtime/entrypoint.py) |
| 129 | chatchat-space__LangGraph-Chatchat | untested | 通用图加载 | langgraph:/app/chatchat-server/chatchat/server/utils.py:get_graph_memory_type | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/129_chatchat-space__LangGraph-Chatchat/runtime/entrypoint.py) |
| 130 | didilili__deepsearch-agents | untested | 通用图加载 | examples/6-langgraph-subagent-wrapper.py:compiled_graph（扫源码找到，非 langgraph.json） | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/130_didilili__deepsearch-agents/runtime/entrypoint.py) |
| 131 | OS3Lab__agent4kdump | untested | 通用图加载 | langgraph:/app/src/agents/search_agent.py:create_search_reviewer_agent | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/131_OS3Lab__agent4kdump/runtime/entrypoint.py) |
| 132 | akamai__patchdiff-ai | untested | 通用命令行驱动 | patchdiff-ai | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/132_akamai__patchdiff-ai/runtime/entrypoint.py) |
| 133 | tarun7r__deep-research-agent | untested | 通用图加载 | langgraph:/app/src/graph.py:create_research_graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/133_tarun7r__deep-research-agent/runtime/entrypoint.py) |
| 134 | kaymen99__personal-ai-assistant | untested | 通用命令行驱动 | cli:/app/app_whatsapp.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/134_kaymen99__personal-ai-assistant/runtime/entrypoint.py) |
| 135 | skygazer42__Weaver | untested | 通用图加载 | langgraph:/app/support_agent.py:create_support_graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/135_skygazer42__Weaver/runtime/entrypoint.py) |
| 136 | Yourdaylight__stock_datasource | untested | 通用命令行驱动 | stock-ds | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/136_Yourdaylight__stock_datasource/runtime/entrypoint.py) |
| 137 | GU-Cryptography__anykb | untested | 通用图加载 | langgraph:/app/backend/src/agent/graph.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/137_GU-Cryptography__anykb/runtime/entrypoint.py) |
| 138 | YUHAO-corn__manufacturing-agents | untested | 通用图加载 | langgraph:/app/manufacturingagents/manufacturingagents/graph/manufacturing_graph_react.py:create_manufacturing_react_graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/138_YUHAO-corn__manufacturing-agents/runtime/entrypoint.py) |
| 139 | EYamanS__texel-studio | untested | 通用命令行驱动 | cli:/app/worker.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/139_EYamanS__texel-studio/runtime/entrypoint.py) |
| 140 | Y-Research-SBU__TimeSeriesScientist | untested | 专用 Python 驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/140_Y-Research-SBU__TimeSeriesScientist/runtime/entrypoint.py) |
| 141 | FeiCoder__BreadFree-Simu | untested | 通用图加载 | langgraph:/app/breadfree/strategies/agent_strategy.py:build_graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/141_FeiCoder__BreadFree-Simu/runtime/entrypoint.py) |
| 142 | CopilotKit__scene-creator-copilot | untested | 通用图加载 | agent/agent.py:graph（扫源码找到，非 langgraph.json） | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/142_CopilotKit__scene-creator-copilot/runtime/entrypoint.py) |
| 143 | FareedKhan-dev__scalable-rag-pipeline | untested | 通用图加载 | services/api/app/agents/graph.py:agent_app（扫源码找到，非 langgraph.json） | blocked | X 阻塞 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/143_FareedKhan-dev__scalable-rag-pipeline/runtime/entrypoint.py) |
| 144 | kaymen99__Upwork-AI-jobs-applier | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/144_kaymen99__Upwork-AI-jobs-applier/runtime/entrypoint.py) |
| 145 | kargarisaac__telegram_link_summarizer_agent | untested | 通用图加载 | ./agent.py:graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/145_kargarisaac__telegram_link_summarizer_agent/runtime/entrypoint.py) |
| 146 | xiongQvQ__AI_Find_Customer | untested | 通用图加载 | langgraph:/app/backend/graph/builder.py:build_graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/146_xiongQvQ__AI_Find_Customer/runtime/entrypoint.py) |
| 147 | itshyao__proxyless-llm-websearch | untested | 通用命令行驱动 | cli:/app/mcp/demo.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/147_itshyao__proxyless-llm-websearch/runtime/entrypoint.py) |
| 148 | langchain-ai__langgraph-fullstack-python | untested | 通用图加载 | ./src/react_agent/graph.py:graph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/148_langchain-ai__langgraph-fullstack-python/runtime/entrypoint.py) |
| 149 | 123-qw-as__Beacon | untested | 通用命令行驱动 | math-agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/149_123-qw-as__Beacon/runtime/entrypoint.py) |
| 150 | BjornMelin__docmind-ai-llm | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/150_BjornMelin__docmind-ai-llm/runtime/entrypoint.py) |
| 151 | iblameandrew__open-deepthink | untested | 通用命令行驱动 | deepthink | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/151_iblameandrew__open-deepthink/runtime/entrypoint.py) |
| 152 | argonne-lcf__ChemGraph | untested | 通用命令行驱动 | chemgraph | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/152_argonne-lcf__ChemGraph/runtime/entrypoint.py) |
| 153 | Ganador1__FenixAI_tradingBot | untested | 通用命令行驱动 | run_fenix.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/153_Ganador1__FenixAI_tradingBot/runtime/entrypoint.py) |
| 154 | EricHong123__B-agent | untested | 通用命令行驱动 | cli:/app/backend/app/main.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/154_EricHong123__B-agent/runtime/entrypoint.py) |
| 155 | hwchase17__autoresearch-agents | untested | 通用图加载 | langgraph:/app/agent.py:build_agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/155_hwchase17__autoresearch-agents/runtime/entrypoint.py) |
| 156 | leonzzz435__garmin-ai-coach | untested | 通用图加载 | langgraph:/app/services/ai/langgraph/workflows/planning_workflow.py:create_planning_workflow | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/156_leonzzz435__garmin-ai-coach/runtime/entrypoint.py) |
| 157 | kevin333353__jobsmith | untested | 通用命令行驱动 | 专用 run_agent；见实现 | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/157_kevin333353__jobsmith/runtime/entrypoint.py) |
| 158 | neopen__story-shot-agent | untested | 通用命令行驱动 | story-shot-agent | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/158_neopen__story-shot-agent/runtime/entrypoint.py) |
| 159 | bamboo-moon__zhisaotong-Agent | untested | 通用命令行驱动 | cli:/app/rag/rag_service.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/159_bamboo-moon__zhisaotong-Agent/runtime/entrypoint.py) |
| 160 | Neon549__Alpha_stock | untested | 通用图加载 | langgraph:/app/agent_runtime/compat/langgraph/scan_graph.py:build_scan_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/160_Neon549__Alpha_stock/runtime/entrypoint.py) |
| 161 | waseens__deep-search-pro | untested | 通用命令行驱动 | cli:/app/rawflow/knowledge_demo.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/161_waseens__deep-search-pro/runtime/entrypoint.py) |
| 162 | colossus-lab__openarg_backend | untested | 通用命令行驱动 | cli:/app/scripts/scaffold_mart.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/162_colossus-lab__openarg_backend/runtime/entrypoint.py) |
| 163 | NVIDIA-AI-Blueprints__biomedical-aiq-research-agent | untested | 通用命令行驱动 | cli:/app/data/sync_files2.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/163_NVIDIA-AI-Blueprints__biomedical-aiq-research-agent/runtime/entrypoint.py) |
| 164 | kaymen99__local-rag-researcher-deepseek | untested | 通用图加载 | ./src/assistant/graph.py:researcher | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/164_kaymen99__local-rag-researcher-deepseek/runtime/entrypoint.py) |
| 165 | ro-anderson__multi-agent-rag-customer-support | untested | 通用图加载 | customer_support_chat/app/graph.py:multi_agentic_graph（扫源码找到，非 langgraph.json） | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/165_ro-anderson__multi-agent-rag-customer-support/runtime/entrypoint.py) |
| 166 | twanew__OmniWriter | untested | 通用图加载 | ./test/search_user_agent.py:create_search_user_graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/166_twanew__OmniWriter/runtime/entrypoint.py) |
| 167 | IatomicreactorI__CSGOTrading | untested | 通用命令行驱动 | cli:/app/run.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/167_IatomicreactorI__CSGOTrading/runtime/entrypoint.py) |
| 168 | jaguarliuu__xunlong | untested | 通用命令行驱动 | cli:/app/src/cli.py | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/168_jaguarliuu__xunlong/runtime/entrypoint.py) |
| 169 | Eldergenix__Plato-Scientific-Research-Autonomous-Agent | untested | 通用命令行驱动 | plato | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/169_Eldergenix__Plato-Scientific-Research-Autonomous-Agent/runtime/entrypoint.py) |
| 170 | bcefghj__medical-multi-agent-system | untested | 通用图加载 | langgraph:/app/python/src/graph/clinical_pipeline.py:build_clinical_pipeline | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/170_bcefghj__medical-multi-agent-system/runtime/entrypoint.py) |
| 171 | agruai__company-research-agent | untested | 通用图加载 | ./langgraph_entry.py:graph | boots | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/171_agruai__company-research-agent/runtime/entrypoint.py) |
| 172 | seanlxh__Air-Lingjing | untested | 通用图加载 | langgraph:/app/backend/app/modules/agents/loop.py:build_graph | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/172_seanlxh__Air-Lingjing/runtime/entrypoint.py) |
| 173 | shodan1q__zeroapp | untested | 通用命令行驱动 | zerodev | invoked | C 仅冒烟 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/173_shodan1q__zeroapp/runtime/entrypoint.py) |
| 174 | bcefghj__agent-knowledge-hub | untested | 通用图加载 | langgraph:/app/python/orchestrator/graph.py:build_knowledge_graph_workflow | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/174_bcefghj__agent-knowledge-hub/runtime/entrypoint.py) |
| 175 | KRATSZ__LabScript-AI | untested | 通用图加载 | langgraph:/app/backend/langchain_agent.py:build_code_agent_graph | scaffold | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/175_KRATSZ__LabScript-AI/runtime/entrypoint.py) |
| 176 | ljxpython__ai-agent-platform | untested | 通用命令行驱动 | cli:/app/apps/platform-api/worker.py | failing | D 未跑通 | [源码](C:/Song_startup/benchmark/wangyi/agents/untested/176_ljxpython__ai-agent-platform/runtime/entrypoint.py) |

## 主要参考

- [Wangyi 主说明](C:/Song_startup/benchmark/wangyi/README.md)
- [适配契约](C:/Song_startup/benchmark/wangyi/tools/CONTRACT.md)
- [留档状态表](C:/Song_startup/benchmark/wangyi/agents/STATUS.md)
- [共享子进程插桩](C:/Song_startup/benchmark/wangyi/tools/_template/parts/sitecustomize.py)
- [Company 原后端](C:/Song_startup/benchmark/AgentBehaviorBench0.0/resources/agents/01-company-research-agent/agent/application.py)
