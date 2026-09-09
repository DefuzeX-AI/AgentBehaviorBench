# 2026 年 Agent 可观测性、执行视图与轨迹诊断调研

检索截止：2026-09-08。服务于 ABB 的讨论场景：输入公司名称，运行原生 Company Research Agent，在网页查看能力、LLM、工具、子 Agent 和跨进程 trace；当前不执行评测 SDK。

## 阅读说明与完整性结论

本报告整理了 **43 项核心及扩展研究条目（P01—P43）**，另列综述、年份边界、工程仓库、协议及待核验线索。排序是与 ABB 的关联程度，不是论文质量排行榜。

**本轮审核结论：已建立较广的可核对目录，不能证明“网上所有 2026 年研究已经找齐”。** 检索覆盖论文原站、会议页面、作者项目页、GitHub，并通过综述和新论文参考文献补漏。仍存在未核验代码、访问受限页面、未逐篇展开的外围研究。不能把本报告当作完成数据库级系统综述、复现或代码安全审计的证明。

年份口径：优先记录 arXiv 首次提交日期；仅写月份的条目保留月份精度。2025 预印本、2026 正式发表另列，避免重复计数。2026 年尚未发生的月份不在时间范围内。GitHub 是本次访问快照，通常没有固定到论文发布时的 commit，因此当前实现与论文版本可能不同。

代码状态：**已见实现**表示访问了作者关联仓库，看到实现目录或程序入口及说明，未安装运行；**作者链接**表示有原始来源指向但没有充分核验实现；**未确认**不等于不存在代码。论文中的“span”可能指语义文本片段，并不自动等于 OpenTelemetry span。

## 最先值得看的内容

| 优先级 | 对象 | 解决什么问题 | 对 ABB 的判断 |
|---|---|---|---|
| 1 | OpenInference + Phoenix；AgentScope Studio | 框架采集、调用树、模型输入输出、token、运行记录 | 最接近先把真实 Agent 跑起来并看 trace 的工程起点；见工程表 E01—E05 |
| 2 | AgentStepper（P01） | 调试 API、独立服务、网页分层；断点、单步、修改调用 | 借鉴边界和交互设计；暂停与重跑放在基础观测之后 |
| 3 | DiLLS（P02） | 长日志按活动、动作、操作分层 | 借鉴页面的信息层次，避免一上来画无法阅读的大图 |
| 4 | AgentDebugX（P13） | Python、CLI、web 共用诊断流程，恢复与验证 | 直接参考多入口设计；它主要围绕诊断轨迹，不自动解决 ABB 的 Agent 生命周期 |
| 5 | Graph of Trace（P03） | 研究流程和产物的实时图 | 可借鉴研究报告视图；主动上报和 LLM 整理的图不能替代原始采集 |
| 6 | DRIFT / TELBench（P16）、SearchAuditor（P21） | 搜索、证据、结论之间的错误定位 | 与 Company Research 高度相关，适合作为后续诊断层 |
| 7 | TraceElephant（P23） | 完整输入上下文与仅输出轨迹的差别 | 决定“所有 trace”究竟要保存哪些信息 |
| 8 | GRADE（P11）、LEDGER（P06）、AgentTrails（P05） | 执行关系、依赖关系、产物和结论证据 | 调用树之外的下一步；推断关系必须标明来源 |

以上是助手建议，尚未冻结为 ABB 的实现选型。

## A. 人能看懂的执行视图与调试器

| ID | 研究、日期、原始来源 | 核心内容与限制 | GitHub / 资源状态 |
|---|---|---|---|
| P01 | [AgentStepper: Interactive Debugging of Software Development Agents](https://arxiv.org/abs/2602.06593)，02-06，预印本 | 结构化对话、断点、单步、运行中修改提示词/工具调用、代码变更。研究针对 coding agents，用户研究规模较小。 | [sola-st/AgentStepper](https://github.com/sola-st/AgentStepper)，已见 API、Core、UI、Evaluation；网页使用 Vue |
| P02 | [DiLLS: Interactive Diagnosis of LLM-based Multi-agent Systems via Layered Summary of Agent Behaviors](https://arxiv.org/abs/2602.05446)，02-05，关联 CHI 2026 DOI | 活动→动作→操作三级组织，支持故障定位与理解。摘要属于整理结果，应能回溯原始日志。 | 本次未确认作者实现仓库；不能把引用 DiLLS 的第三方 issue 算作代码 |
| P03 | [Graph of Trace: Visualizing Execution Traces of Scientific Agents](https://aclanthology.org/2026.acl-demo.29/)，06-13 预印本，ACL 2026 Demo / 7 月 | 研究任务实时 DAG。当前仓库由 Agent 调用 build_trace MCP 工具，LLM 提取节点后写 got.json；不是被动截获全部工具和模型请求。 | [NeuroAIHub/Graph-of-Trace](https://github.com/NeuroAIHub/Graph-of-Trace)，已见 Monitor、frontend、server.py、tool.py、tests |
| P04 | [TraceView: Interactive Visualization of Agentic Program Repair Trajectories](https://arxiv.org/abs/2606.22110)，06-20，预印本 | Thought/Action/Result 图、关系筛选、节点证据、补丁结果。面向已有轨迹的标注和分析，非通用实时 OTLP 接收器。 | [SOAR-Lab/agent-traj-visualization](https://github.com/SOAR-Lab/agent-traj-visualization)，已见 Streamlit 应用 traceview_app 与样本 |
| P05 | [AgentTrails: Towards Trust and Reuse for Agentic Tasks](https://arxiv.org/abs/2607.18816)，07-21；正文标注 VLDB 2026 DASHSys workshop | 把工具调用和数据产物变成溯源图，比较多次执行、观察工具覆盖和依赖。属于原型；时间先后不等于数据依赖。 | 本次未确认论文作者代码；搜索到的同名 agenttrails-samples 不据此关联 |
| P06 | [LEDGER: Claim-to-Evidence Trace Graphs for Auditing LLM Agents](https://arxiv.org/abs/2608.18398)，08-19，预印本 | 原始记录、证据节点、工作流节点分层，把结论关联到动作、产物和检查。适合报告的“这句话从哪里来”。 | 本次未确认作者代码；不是凭名称关联区块链 Ledger 项目 |
| P07 | [Artifact-centered Claim-aware Observability for Autonomous Scientific Agents](https://arxiv.org/abs/2608.18312)，08-18，预印本 | 科学产物谱系、结论证据绑定、验证记录；补充 OTel 的语义层。偏框架/立场，不等于已交付通用控制台。 | 本次未确认作者实现仓库 |

## B. 采集语义、跨边界关联与图表示

| ID | 研究、日期、原始来源 | 核心内容与限制 | GitHub / 资源状态 |
|---|---|---|---|
| P08 | [AgentTrace: A Structured Logging Framework for Agent System Observability](https://arxiv.org/abs/2602.10133)，02-07 arXiv；另有 [AAAI 2026 workshop 版本](https://trustagenticai.github.io/AAAI2026/AAAI-Workshop/73.pdf) | 从操作、认知、上下文三类记录组织运行观测。认知记录仍受系统实际暴露的数据限制，不能据此承诺模型隐藏推理。 | 本次未确认 AlSayyad / Huang / Pal 对应代码；与 Rxflex/agenttrace 等同名仓库严格区分 |
| P09 | [AgentTelemetry: A Fault Detection Benchmark and Toolkit for LLM Agent Observability](https://doi.org/10.1145/3805760.3814931)，AIware 2026 / 7 月；作者仓库给出出版信息与归档 | OTel 上扩展 agent span 类型、框架适配、故障分析。仓库明确区分 schema 能表达什么与 adapter 实际发出了什么；mock 故障注入结果不能等价于生产检测率。 | [Krishnachaitanyakc/AgentTelemetry](https://github.com/Krishnachaitanyakc/AgentTelemetry)，已见包、benchmark、论文材料；AIware 快照与后续 MDE 实验需分开 |
| P10 | [Observability for Delegated Execution in Agentic AI Systems](https://arxiv.org/abs/2606.09692)，06-08，预印本 | 委托上下文在执行时绑定，跨工具重建责任/授权范围。仅有调用因果关系未必足以推断委托关系。 | 本次未确认作者代码 |
| P11 | [GRADE: Graph Representation of LLM Agent Dependency and Execution](https://arxiv.org/abs/2606.22741)，06-22，预印本 | 执行边与依赖边两层；依赖标明 observed / declared / inferred。适合避免 ABB 把 LLM 猜出的边画成确定事实。 | [yzhao062/grade](https://github.com/yzhao062/grade)，已访问作者仓库；未做复现 |

## C. 故障诊断、研究任务审计与修复

| ID | 研究、日期、原始来源 | 核心内容与限制 | GitHub / 资源状态 |
|---|---|---|---|
| P12 | [AgentRx: Diagnosing AI Agent Failures from Execution Trajectories](https://arxiv.org/abs/2602.02475)，2 月，预印本 | 从轨迹构造约束并检查，定位关键失败步骤。处理已产生的轨迹；不是原生 Agent 运行管理器。 | [microsoft/AgentRx](https://github.com/microsoft/AgentRx)，已见实现；本地已有先前代码阅读记录 |
| P13 | [AgentDebugX: An Open-Source Toolkit for Failure Observability, Attribution, and Recovery in LLM Agents](https://arxiv.org/abs/2607.18754)，07-21；仓库标注 EMNLP 2026 Demo | Detect→Attribute→Recover→Rerun；library、CLI、web、skill。真实重跑仍依赖调用方配置 runner，不能把计划/模拟当成已重跑。 | [AgentDebugX/AgentDebugX](https://github.com/AgentDebugX/AgentDebugX)，已见 src、integrations、tests；[官方文档](https://www.agentdebugx.com/docs) |
| P14 | [TRAJDEBUG: Tracing Error Lifecycle to Identify Critical Failures in Long-Horizon Agent Trajectories](https://arxiv.org/abs/2608.06346)，08-06；仓库标注 EMNLP 2026 Findings | 多粒度轨迹→错误触发→解决状态/终局影响→关键归因，附 TrajErrBench。要区分被纠正的局部错误和导致终局失败的错误。 | [THU-KEG/TrajDebug](https://github.com/THU-KEG/TrajDebug)，当前已见 detector、data、pipeline 与 viewer 说明；旧搜索摘要“待公开”已纠正 |
| P15 | [TraceSIR: A Multi-Agent Framework for Structured Analysis and Reporting of Agentic Execution Traces](https://arxiv.org/abs/2603.00623)，02-28，预印本 | StructureAgent→InsightAgent→ReportAgent；轨迹压缩、局部诊断、跨任务报告。附 TraceBench / ReportEval，属于分析层。 | [SHU-XUN/TraceSIR](https://github.com/SHU-XUN/TraceSIR)，已见 pipeline.py、app.py、templates、TraceBench |
| P16 | [Where Do Deep-Research Agents Go Wrong? Span-Level Error Localization in Agent Trajectories](https://arxiv.org/abs/2606.02060)，06-01，DRIFT / TELBench | 追踪结论首次提出、复用和成为有害承诺的过程，区分正常探索与有害错误。这里的 semantic spans 不是天然的 OTLP spans。 | [NJU-LINK/DRIFT](https://github.com/NJU-LINK/DRIFT)，已见 src/drift_open、scripts、tests；TELBench 数据获取见仓库 |
| P17 | [From Failed Trajectories to Reliable LLM Agents: Diagnosing and Repairing Harness Flaws](https://arxiv.org/abs/2606.06324)，06-04，HarnessFix | 原始轨迹和 harness 代码→HTIR→诊断→修复→验证。值得参考环境、工具包装、完成条件也可能导致失败这一问题划分。 | [HarnessFix/HarnessFix](https://github.com/HarnessFix/HarnessFix)，已见分析/修复/评估代码与 harness 快照；原始数据、trace、日志并非全部包含 |
| P18 | [CodeTracer: Towards Traceable Agent States](https://arxiv.org/abs/2604.11641)，04-13，预印本 | 异构运行产物→分层状态轨迹→失败起点和传播链；CodeTraceBench 支持阶段与步骤定位。不同版本数据量需以对应版本为准。 | [NJU-LINK/CodeTracer](https://github.com/NJU-LINK/CodeTracer)，已访问实现仓库 |
| P19 | [From Flat Logs to Causal Graphs: Hierarchical Failure Attribution for LLM-based Multi-Agent Systems](https://arxiv.org/abs/2602.23701)，02-27，CHIEF | 分层因果图、oracle 引导回溯、反事实归因。适合诊断表示；不能仅凭时序自动认定因果。 | [Mr-Capybara/CHIEF](https://github.com/Mr-Capybara/CHIEF) 自称论文实现；作者归属关联未充分确认，按候选实现处理 |
| P20 | [TrajAudit: Automated Failure Diagnosis for Agentic Coding Systems](https://arxiv.org/abs/2605.26563)，05-26，预印本 | 过滤 coding 轨迹噪声、从测试失败形成先验、按需恢复上下文；附 RootSE。RootSE 是此论文的 benchmark，避免当作另一篇重复统计。 | [LogAnalysisTech/TrajAudit](https://github.com/LogAnalysisTech/TrajAudit)，已见实现/结果组织 |
| P21 | [SearchAuditor: Auditing and Attributing Failures in Long-Horizon Search Agents](https://arxiv.org/abs/2608.05212)，8 月，预印本 | 搜索 Agent 的定位、归因和修复，附 SearchAuditBench。与公司研究任务相关，后续值得精读其证据裁决方式。 | 本次未确认作者实现仓库；第三方 reading list 不当作代码 |
| P22 | [LongRCA Bench: Diagnosing Responsible Roles and Root Causes in Long-Horizon Agent Failures](https://arxiv.org/abs/2608.15242)，8 月，预印本 | 长程失败中的责任角色与根因诊断。用于后续检验诊断质量，而非第一阶段采集。 | 本次未确认作者实现仓库 |

## D. 过程评测、归因方法与记忆诊断

| ID | 研究、时间、原始来源 | 与 ABB 的关系 | GitHub / 资源状态 |
|---|---|---|---|
| P23 | [Seeing the Whole Elephant: A Benchmark for Failure Attribution in LLM-based Multi-Agent Systems](https://arxiv.org/abs/2604.22708)，04-24，ACL 2026，TraceElephant | 强调保存输入和上下文，而非只保留 Agent 输出；提供可复现环境和失败标注。 | [TraceElephant/TraceElephant](https://github.com/TraceElephant/TraceElephant)，已见 code 和数据/环境说明 |
| P24 | [AgentProcessBench: Diagnosing Step-Level Process Quality in Tool-Using Agents](https://arxiv.org/abs/2603.14465)，03-15 | 步骤级过程质量；探索、错误和最终失败不能粗暴混成一个标签。 | [RUCBM/AgentProcessBench](https://github.com/RUCBM/AgentProcessBench)，已见 annotation_platform、data、eval、utils |
| P25 | [Rethinking Failure Attribution in Multi-Agent Systems: A Multi-Perspective Benchmark and Evaluation](https://arxiv.org/abs/2603.25001)，03-26，MP-Bench | 同一失败可能存在多个合理归因，界面应容纳证据、置信度与不同观点。 | [yeonjun-in/MP-Bench](https://github.com/yeonjun-in/MP-Bench)，论文链接且已访问仓库 |
| P26 | [Towards Self-Improving Error Diagnosis in Multi-Agent Systems](https://arxiv.org/abs/2604.17658)，04-19，ErrorProbe；摘要注明 ACL 2026 Findings | 局部异常→症状回溯→工具验证，确认后更新诊断记忆。 | 本次未确认作者代码 |
| P27 | [MASPrism: Lightweight Failure Attribution for Multi-Agent Systems Using Prefill-Stage Signals](https://arxiv.org/abs/2605.07509)，5 月 | 借助小模型 prefill 信号降低归因成本；需要的模型信号不应成为任意原生 Agent 的强制接入要求。 | [Zenodo 软件归档](https://zenodo.org/records/19940111) 指向 Lycc42/masprism-ase26-artifact；本次 GitHub 打开失败，归档线索待复核 |
| P28 | [VerifyMAS: Hypothesis Verification for Failure Attribution in LLM Multi-Agent Systems](https://arxiv.org/abs/2605.17467)，5 月 | 验证归因假设，适合后续诊断插件。 | [mala-lab/VerifyMAS](https://github.com/mala-lab/VerifyMAS)，已访问官方实现仓库 |
| P29 | [FALAT: Tracing Failures in LLM Agent Trajectories via Dependency-Guided Search](https://arxiv.org/abs/2606.00765)，6 月 | 沿依赖进行故障搜索，补充平面日志检查。 | 本次未确认作者代码 |
| P30 | [ASCon: A Direction-Aware Reciprocal Agent–Step Contextualization Model for Failure Attribution in Multi-Agent Systems](https://arxiv.org/abs/2608.10646)，08-11 | 对 agent、步骤和错误类型联合建模；需要训练/模型支持的归因层。 | [Shuyu-07/ASCon](https://github.com/Shuyu-07/ASCon)，论文链接且已访问仓库 |
| P31 | [Adaptive Influence Graphs for Failure Attribution in Multi-Agent Systems](https://arxiv.org/abs/2608.24361)，08-25 | 先构造有结构的影响图，再由诊断 Agent 导航；说明轨迹表示本身影响归因效果。 | 本次未确认作者代码 |
| P32 | [MemTrace: Tracing and Attributing Errors in Large Language Model Memory Systems](https://arxiv.org/abs/2605.28732)，5 月 | 跟踪记忆系统中的错误及来源，适合研究 Agent 读写长期记忆后的扩展观测。 | [zjunlp/MemTrace](https://github.com/zjunlp/MemTrace)，已见实现；与 OCaml profiler、同名记忆产品不同 |
| P33 | [The Why Behind the Action: Unveiling Internal Drivers via Agentic Attribution](https://arxiv.org/abs/2601.15075)，01-21 | 从历史步骤与句子分析行为影响；方法使用概率/扰动信号，不能将其等同于普通 OTel 能提供的解释。 | 本次未确认作者代码 |

## E. 在线监控、重跑预算及安全扩展

| ID | 研究、时间、原始来源 | 与 ABB 的关系 | GitHub / 资源状态 |
|---|---|---|---|
| P34 | [TRACE: Trajectory Reasoning through Adaptive Cross-Step Evidence Aggregation for LLM Agents](https://arxiv.org/abs/2606.07054)，06-05 | Triage→Inspect→Judge 累积跨步骤证据，检测长轨迹破坏行为。安全审计用途，非通用 trace 采集框架。 | 本次未确认作者代码 |
| P35 | [Monitoring Web Agents Without Internal Signals: Observable Trajectories and Key-Step Supervision](https://arxiv.org/abs/2609.02057)，09-02，预印本 | 只用可观测轨迹预测前缀风险，适合闭源模型；需要额外预测器/黑盒查询，非“零成本全知”。 | 本次未确认作者代码 |
| P36 | [AgentForesight: Online Auditing for Early Failure Prediction in Multi-Agent Systems](https://arxiv.org/abs/2605.08715)，05-09 | 对进行中的轨迹前缀做早期审计；训练数据和判定器是独立研究部分。 | [作者项目页](https://zbox1005.github.io/agent-foresight/)可定位，但本次正文抓取为空；代码待确认 |
| P37 | [Leveraging Trajectory Graphs for Pre-Execution Error Diagnosis in Agentic LLM Systems](https://arxiv.org/abs/2607.27443)，07-29 | 执行动作前的图结构诊断。应与事后根因定位分开衡量。 | 本次未确认作者代码；与检索中的 Trajectory Graph Copilot 是否同一版本尚未充分核验 |
| P38 | [Knowledge-Based Zero-Replay Debugging of Multi-Agent LLM Traces](https://arxiv.org/abs/2606.14805)，06-11 | 用结构化事件图预测值得花重跑预算的步骤；并不意味着无需真实环境就验证了修复。 | 本次未确认作者代码；论文标为投稿版本，非已录用声明 |
| P39 | [Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses](https://arxiv.org/abs/2604.25850)，04-28，AHE | 可编辑组件、可下钻轨迹证据、修改效果验证；是观测之后的自动优化闭环。 | [china-qijizhifeng/agentic-harness-engineering](https://github.com/china-qijizhifeng/agentic-harness-engineering)，已见 agents、configs、evolve.py、trace_converter.py |
| P40 | [ATBench: A Diverse and Realistic Agent Trajectory Benchmark for Safety Evaluation and Diagnosis](https://arxiv.org/abs/2604.02022)，4 月 | 安全轨迹评测与诊断，适合未来扩展安全维度。搜索摘要存在旧标题，本文采用当前论文页标题。 | 本次未确认作者代码 |
| P41 | [SciTrace: Trajectory-Aware Safety Reasoning for Scientific Discovery Agents](https://arxiv.org/abs/2606.08234)，6 月 | 科学工作流和组合工具链的轨迹安全分析；不是第一阶段运行 UI 的依赖。 | 本次未确认作者代码 |
| P42 | [Notarized Agents: Receiver-Attested Confidential Receipts for AI Agent Actions](https://arxiv.org/abs/2606.04193)，06-02，Sello | 让接收服务签署动作回执，研究不完全信任 Agent 自报日志时的证据问题。协议提案，有部署与采用条件。 | 本次未确认作者代码 |
| P43 | [Scope Delineation Before Localization: A Two-Stage Framework for Enhancing Failure Attribution in Multi-Agent Systems](https://ojs.aaai.org/index.php/AAAI/article/view/40594)，AAAI 2026 正式出版 03-14 | 先缩范围再定位的多 Agent 归因；按 2026 正式出版口径收录，未据此声称首次预印本也在 2026。 | 本次未确认作者代码 |

## F. 综述、架构研究与年份边界

| 对象 | 来源与状态 | 用途 / 边界 |
|---|---|---|
| A Survey for LLM Agent Trajectory Analysis: From Failure Attribution to Enhancement | [作者维护的目录](https://github.com/IcyFeather233/Awesome-LLM-Agent-Trajectory-Analysis)，列出 TSE 2026、DOI 10.1109/TSE.2026.3717765；本次以作者材料作为引文扩展入口 | 覆盖失败分类、归因、增强、监控与 benchmark。目录会继续更新；其“覆盖到 4 月”描述与后来加入的 8 月工作不能混为固定时间快照 |
| Agent Harness Engineering: A Survey | [作者项目页](https://picrew.github.io/LLM-Harness/)，另有 OpenReview PDF；首次发表日未充分核验 | Execution、Tooling、Context、Lifecycle、Observability、Verification、Governance 的分层可辅助 ABB 讨论；不能因参考列表把 OTel 写成 2026 就说 OTel 始于 2026 |
| Harness Engineering: Anatomy, Architecture, and Evolution of Coding Agents — A Source-Code Study of Eleven Systems | [arXiv:2609.00006](https://arxiv.org/abs/2609.00006)，2026 年新近工作 | 原生 coding agent 架构的源码研究，作为去框架强制绑定的扩展阅读；本次未逐一核验其对全部系统的源码结论 |
| Open Agent Specification: Enabling Cross-Framework Comparison of AI Agents | [2026 ACM 论文](https://doi.org/10.1145/3786335.3813130)、[oracle/agent-spec](https://github.com/oracle/agent-spec) | 跨框架声明与运行映射；[技术报告](https://arxiv.org/abs/2510.04173)首次提交在 2025，应区分版本。不能推导为 ABB 必须要求所有 Agent 改写成此 DSL |
| XAgen | [论文](https://arxiv.org/abs/2512.17896)首次提交 2025-12；本次未充分核验正式会议年份和官方代码 | 界面、解释、纠错相关，作为年份边界，未塞进 2026 首发集合 |
| AGDebugger | [论文](https://arxiv.org/abs/2503.02068)，2025；[microsoft/agdebugger](https://github.com/microsoft/agdebugger)为检索到的代码线索，未独立检查仓库 | 多 Agent 交互调试的前作 |
| AgentSight | [eunomia-bpf/agentsight](https://github.com/eunomia-bpf/agentsight)，论文前作为 2025 | 系统级 eBPF 观测的重要工程参考；不是 2026 新论文 |
| Agent Trajectory Explorer、AgentDiagnose、AgentDebug / AgentErrorBench、Who&When、TRAIL | 在上述综述和原始论文参考文献中找到，主要为 2025 工作 | 作为引文与数据来源；不能把 2026 页面更新日期当作首次发表日期 |

## G. GitHub 工程项目与协议

这一表是 **2026 年检索时可参考的工程生态**，不要求项目首次发布于 2026，也不计入 P01—P43。论文附带仓库已在前面列出。未使用 stars 排名；未安装、上传 ABB 数据或调用模型。

| ID | 仓库 / 原始文档 | 提供的层次 | 与 ABB 的接入关系与限制 |
|---|---|---|---|
| E01 | [Arize-ai/openinference](https://github.com/Arize-ai/openinference) | OTel 的 AI 语义和 Python / JS 等 instrumentation | 可借鉴框架到 span 的适配；不负责下载和启动任意 Agent |
| E02 | [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) | trace 服务、UI、查询、数据集与评测 | 原生 Agent 带 instrumentation 向服务发送 trace；平台和轻量采集/客户端包分开。可先用来核对采集结果 |
| E03 | [traceloop/openllmetry](https://github.com/traceloop/openllmetry) | 基于 OTel 的模型和框架采集 | 与 E01 对照 adapter 范围；采集包不等于整个可自部署平台 |
| E04 | [langfuse/langfuse](https://github.com/langfuse/langfuse) | 观测、prompt、评测与数据管理平台 | 可参考 run/observation/LLM 详情和自托管；仍需接入 Agent 的实际执行路径 |
| E05 | [agentscope-ai/agentscope-studio](https://github.com/agentscope-ai/agentscope-studio) | Projects/Runs、实时交互、OTel trace、token、Agent 调用 | 与“手术台”形态接近；官方接入示例绑定 AgentScope initializer；不能直接推定任意下载 Agent 零改造接入 |
| E06 | [AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops) | Python 采集 SDK、成本和框架集成 | 核对 SDK 与托管平台边界；仓库公开不自动说明 dashboard 服务端全部公开 |
| E07 | [future-agi/traceAI](https://github.com/future-agi/traceAI) | 多语言、多框架 OTel instrumentation | 可补框架覆盖；README 支持列表不是 ABB 实际兼容性验证 |
| E08 | [mlflow/mlflow](https://github.com/mlflow/mlflow) | tracing、实验、评测与 UI | 与未来 benchmark 结果和 trace 关联有参考价值；起源早于 2026 |
| E09 | [wandb/weave](https://github.com/wandb/weave) | AI 应用追踪和评测工具 | 区分开源库与服务部署范围，不能因 SDK 开源就推定完整后端开源 |
| E10 | [eunomia-bpf/agentsight](https://github.com/eunomia-bpf/agentsight) | 系统/进程边界的观测 | 可补程序外部的执行证据；系统事件、网络流量不自动揭示业务节点与完整语义；有运行平台条件 |
| E11 | [ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui) | Agent 到用户界面的事件协议，支持 SSE 等传输 | 候选交互协议；消息/状态/工具事件并不能替代 OTLP 原始 spans 与历史查询 |
| E12 | [open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) | GenAI、MCP、模型调用等遥测语义 | 本次发现原 semantic-conventions 中 GenAI 页面已标记迁移；选型时必须固定规范/adapter 版本，避免照抄过期字段 |
| E13 | [OTel context propagation](https://opentelemetry.io/docs/concepts/context-propagation/) | trace context 的 inject / extract | 跨进程关联的基础；发到同一个 Collector 不代表自动接成同一调用树 |
| E14 | [Red Hat 2026-04-06 实践](https://developers.redhat.com/articles/2026/04/06/distributed-tracing-agentic-workflows-opentelemetry)、[it-self-service-agent](https://github.com/rh-ai-quickstart/it-self-service-agent) | Python、多个服务、事件、MCP、Collector 的贯通例子 | 直接参考上下文传播和模型/工具 span；文章明确记录部分 MCP 调用需手动传播的版本限制 |
| E15 | [Foundry Agent Inspector 官方说明](https://code.visualstudio.com/docs/intelligentapps/agent-inspector)，页面日期 2026-03-17 | Agent 发现、流式输入输出、工作流图、debugpy | 展示 HTTP server / SSE / webview / run_stream 的分工；这里引用的是官方架构文档，未确认独立完整 GitHub 服务端仓库 |
| E16 | [velodb/agentlogsbench](https://github.com/velodb/agentlogsbench)、[2026-05-15 作者说明](https://www.velodb.io/blog/agentlogsbench-apache-doris-in-ai-observability) | trace 文本检索、回放、聚合查询的数据库 benchmark | 测观测存储查询，非测 Agent 智能。由数据库厂商发布，结果要看查询、资源、索引公平性 |
| E17 | [agentic-control-plane/agentgovbench](https://github.com/agentic-control-plane/agentgovbench) | 身份、策略、观测等治理场景测试 | 软件 benchmark / 厂商自测，非已验证学术结论；不作为第一版页面基础 |

**入口结论（基于这些实现的综合判断）：** 没有必要强制 Agent 通过 ABB CLI 执行。更值得参考的是 library/core、启动环境、telemetry 接入、web 服务分别有明确职责。一个项目提供 CLI 仅说明它有命令行入口，不说明所有被接入 Agent 必须实现相同命令行协议。

## H. 对 ABB 的具体架构启示

以下是从研究中提炼的设计建议，不是当前 ABB 已实现功能。

### 1. 先保留事实，再整理和诊断

```text
输入公司名 → ABB 执行服务 → 原生 Agent 入口 → 搜索 / 读网页 / 模型 / 子 Agent → 报告

实际执行点的 instrumentation
→ 原始 spans + 运行事件 + 产物引用
→ 接收、关联、存储
→ 网页调用树 / 时间线 / 模型与工具详情
→ 后续可选：轨迹摘要、证据图、失败诊断、SDK 评测
```

Graph of Trace 和 DiLLS 的整理视图、LEDGER 的证据关联、AgentRx 的诊断结果，都可以是原始记录之上的附加层。图中关系若由 LLM 推断，应该标成推断，并保留源事件 ID。GRADE 的来源区分直接支持这种做法。[GRADE](https://arxiv.org/abs/2606.22741)

### 2. 跨进程有两条不同的线路

```text
执行请求：调用方注入 trace context → HTTP / 消息 / 子进程载体 → 被调方提取并继续 span
遥测上传：各进程的 exporter → OTLP receiver / Collector → 存储 → 查询与网页
```

二者都要做。Collector 接收不到根本没产生的 span，也不能可靠补出丢失的父子关系。对子进程应明确上下文载体和运行关联，不能只用时间接近推断属于同一次任务。[OTel](https://opentelemetry.io/docs/concepts/context-propagation/)、[Red Hat 实践](https://developers.redhat.com/articles/2026/04/06/distributed-tracing-agentic-workflows-opentelemetry)

### 3. 网页协议与 trace 协议分工

| 边界 | 最小职责 | 候选方式 |
|---|---|---|
| 网页→运行服务 | 列 Agent/能力、提交输入、查询状态、取消 | HTTP API；输入有明确 schema |
| 运行服务→网页 | 实时状态、输出、工具进度 | SSE 或 AG-UI 事件 |
| Agent/工具进程→观测服务 | 原始 span 上传 | OTel + OTLP |
| 网页→历史数据 | 获取整次 trace、节点详情、产物 | 查询 API |

React 只是实现网页的选择。AG-UI 可帮助交互事件标准化，OTLP 负责遥测；两者不必揉成一个协议。[AG-UI](https://github.com/ag-ui-protocol/ag-ui)

### 4. “所有 trace”应能验收

建议为 Company Research 最小场景写一张采集覆盖表：根调用、真实模型调用、搜索与读网页工具、框架节点、子 Agent、跨进程边界、异常/重试/取消、最终产物，各自标明采集来源和已验证状态。

没有观测到的类型显示“未覆盖/未知”，而不是零次；工具已声明但本次没执行，与工具实际执行过是两个字段。还要能发现 span 丢失、父 span 缺失、进程崩溃后的未完成运行。TraceElephant 支持保留输入上下文的必要性，AgentTelemetry 的 adapter 覆盖差异说明只选定 schema 还不够。[TraceElephant](https://arxiv.org/abs/2604.22708)、[AgentTelemetry](https://github.com/Krishnachaitanyakc/AgentTelemetry)

### 5. 第一阶段不需要把这些论文都实现

建议先证明“一只真实 Agent 的输入→执行→输出→跨进程 trace→网页可查”闭环。再增加可下钻摘要和研究结论证据；最后讨论自动归因、修改后重跑、评测 SDK。基础观测不应依赖昂贵诊断模型调用才能使用。

## I. 每轮检索与审核记录

### 第一轮：宽检索

使用 agent observability / tracing / OpenTelemetry / trajectory visualization / debugging / failure diagnosis / benchmark + 2026。发现 AgentStepper、AgentTrace、AgentRx、AgentTelemetry、TrajDebug、HarnessFix 等。

审核：**未找齐。** 交互研究、过程 benchmark 和近期工作覆盖不足。混入 Java tracing agent、微服务 RCA、营销比较文章；移出核心研究集合。

### 第二轮：综述与引文扩展

从作者维护的 trajectory-analysis 目录和相关论文扩展至 DiLLS、TraceView、DRIFT、TraceElephant、AgentProcessBench、CodeTracer。打开论文正文查找作者 GitHub，再访问仓库。

审核：**仍未找齐。** 发现同名项目和年份混淆；AgentTrace、MemTrace、TraceView 不能只按名称配对。TrajDebug 当前仓库推翻旧搜索摘要中的“尚未公开”状态。旧论文和 2026 会议版本分开。

### 第三轮：7—9 月与表示层补漏

增加日期限定、arXiv/ACL/ACM 站点检索及中文查询，补出 AgentDebugX、LEDGER、Artifact-centered Observability、AgentTrails、GRADE、9 月 Web Agent 监控论文。沿较新 AIG 论文参考文献补出 ErrorProbe、MASPrism、VerifyMAS、FALAT、CHIEF、AgentForesight。

审核：**不能宣布全覆盖。** 已补主要视图、采集、诊断、在线监控、证据图类别；自动增强与安全研究范围很大，按关联程度收录扩展项，保留其余候选。

### 第四轮：工程与状态核对

核对论文代码和 OTel / OpenInference / Phoenix / Langfuse / OpenLLMetry / AgentScope Studio / AG-UI 等原始仓库；补上 Red Hat 跨服务示例。专项查询 SearchAuditor、LongRCA、MemTrace、TrajAudit 和剩余代码链接。9 月泛检索新增结果主要为产品文章或尚未举行的活动，未将其充作学术论文。

审核：**完成本轮调研交付，完整性仍是“有已知边界的覆盖”，不是“全网找齐”。** 未能核验的代码明确标注；对访问失败的页面不作确定性判断。未执行论文代码，因此没有“全部可运行/已复现”的结论。

### 检索词记录（代表性原样查询，可用于复查）

```text
2026 agent observability tracing OpenTelemetry paper github
2026 LLM agent execution trajectory visualization debugging paper github
2026 agent failure diagnosis root cause trajectory benchmark github
2026 agent observability benchmark distributed tracing research
2026 agent trace visualization debugger arxiv AgentStepper
2026 LLM agent failure localization diagnosis survey github
2026 "agent" "visualization" "debugging" site:arxiv.org
2026 agent observability "survey" arxiv
2026 "agent" "visual analytics" debugging
2026 "agent" "OpenTelemetry" paper -site:reddit.com
"agent" "trace" "visualization" "2026" site:arxiv.org/abs after:2026-07-01
"agent" "observability" "2026" site:arxiv.org/abs after:2026-07-01
2026 "failure attribution" "agent" site:arxiv.org/abs
2026 智能体 可观测性 轨迹 可视化 调试 论文
"2026" "agent observability" research "September" -site:reddit.com
```

另执行了论文/方法精确名称 + github 查询，并用论文 HTML 的 GitHub 链接反查；这里不是搜索引擎返回结果的完整逐条日志。

### 覆盖矩阵

| 类别 | 已覆盖的代表 | 审核结论 / 剩余缺口 |
|---|---|---|
| 实时/交互 UI | AgentStepper、DiLLS、Graph of Trace、AgentScope Studio | 形态覆盖；未进行所有产品实机对比 |
| 异构 Agent instrumentation | AgentTelemetry、OpenInference、OpenLLMetry、traceAI | 工程覆盖；尚未测试 ABB Agent 与具体版本兼容 |
| 跨进程 | OTel propagation、Red Hat 示例、delegation 研究 | 基础机制有直接来源；容器/线程/队列/异步边界未逐种实验 |
| LLM 输入输出/成本 | Phoenix、Langfuse、AgentOps、MLflow、Weave | 工程参考覆盖；内容捕获与计费精度依赖配置和 provider |
| 长轨迹和错误归因 | AgentRx、AgentDebugX、CHIEF、TrajDebug、FALAT 等 | 研究谱系较广；未逐篇复现全部归因算法 |
| Research Agent | DRIFT、SearchAuditor、Graph of Trace、AgentTrails | 高相关覆盖；未用真实公司研究任务进行外部有效性验证 |
| 状态/记忆/产物 | CodeTracer、MemTrace、LEDGER、GRADE | 基本类别覆盖；更广 provenance/security 文献未全量展开 |
| 过程/归因 benchmark | TraceElephant、AgentProcessBench、MP-Bench、LongRCA | 已发现主要相关资源；未下载所有数据比对 |
| 在线风险/安全 | AgentForesight、Web Agent Monitoring、TRACE、ATBench、SciTrace | 选择性扩展，不能宣称覆盖全部 Agent 安全文献 |
| 存储和开销 | AgentLogsBench；ICPE tracing 开销研究作为外围 | 厂商偏差/资源公平性尚未复现；不用于决定 ABB 数据库 |

## J. 待核验与排除项

| 线索 | 当前处理和原因 |
|---|---|
| [ICLR 2026 Agents in the Wild 的另一篇 AGENTTRACE PDF](https://openreview.net/attachment?id=22qiB2JpzZ&name=pdf) | 搜索摘要呈现因果图定位，与 P08 作者/主题不同；OpenReview 访问失败，未核验完整题名/作者/代码，未合并或计入 |
| [Trajectory Graph Copilot](https://openreview.net/pdf?id=ighxnB6nJF) | 搜索结果显示 ICLR 2026 投稿；与 P37 的关系待核验，不能当成已接收或第二篇独立论文 |
| [A federated observability architecture pattern…](https://www.sciencedirect.com/science/article/pii/S0950584926002491) | 搜索结果标为 November 2026 卷期，正文打开失败；online-first 日期未确认，未计入截止日内核心集合 |
| [Observability and Causal Tracing for Agentic Data Pipelines…](https://www.acadlore.com/article/ATAIML/2026_5_3/ataiml050305) | 已发现 2026 线索；实验和代码未充分核验，单列待读，不用其指标支撑 ABB 选型 |
| [Towards Log Analysis for Reliability Engineering of Agentic Systems](https://conf.researchr.org/details/icsme-2026/icsme-2026-nier/19/Towards-Log-Analysis-for-Reliability-Engineering-of-Agentic-Systems) | 2026 会议页面已读，是 vision paper / 研究议程，非可运行系统；可作为后续理论补充 |
| [Agent-Native Telemetry](https://arxiv.org/abs/2608.16178) | 主要为给运维 Agent 消费的可验证系统遥测；与记录 Agent 自身执行不同，外围参考 |
| [Beyond Task Success](https://arxiv.org/abs/2604.19818) | 治理、编排、保证的证据综合框架；范围更广，外围参考 |
| [Workstream](https://arxiv.org/abs/2604.17055) | 开发工作整合平台含 Agent 观测，非专门 trace 研究；未做仓库复核 |
| [另一篇 MemTrace](https://arxiv.org/abs/2606.17328) | 长期记忆的受控评测，题目为 Probing What Final Accuracy Misses in Long-Term Memory；与 P32 分开，未展开研究 |
| [o11y-bench](https://grafana.com/blog/o11y-bench-open-benchmark-for-observability-agents/)、Cloud-OpsBench | 用 Agent 排查监控/系统故障的 benchmark；不属于本报告核心“观察 Agent 自身”方向 |
| [Benchmarking the Overhead of Distributed Tracing Agents](https://icpe2026.spec.org/preprint/Benchmarking_the_Overhead_of_Distributed_Tracing_Agents_2.pdf) | ICPE 2026，但 agent 指 Java tracing agent；性能研究外围，不算 LLM Agent 可观测性新方法 |
| GitHub 个人演示、第三方 AgentDoctor / ATFD、纯营销“2026 最佳工具”文章 | 缺乏可验证论文归属或独立评测时不混入学术研究结论；个人代码并不因此无价值 |
| 截止日后的活动，例如 2026-09-10 Conf42 | 可作为未来线索，不能声称已阅读尚未发布的演讲内容 |

后续每次补充应重复：去重→核对首发/会议年份→确认论文和代码归属→记录仓库发布状态→检查类别缺口→更新本审核记录。新发现不能静默覆盖先前错误，应保留修正说明。本次不创建定时监控，亦不改变 ABB 的运行实现。
