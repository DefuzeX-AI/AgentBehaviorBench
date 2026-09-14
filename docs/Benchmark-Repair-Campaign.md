# Issue 修复与真实 Benchmark 验收

授权：2026-09-14 用户批准修复问题、按 Issue 编号建测试、下载接入 TradingAgents / GPT Researcher，并使用现有 API key 运行真实 benchmark。

## 完成条件与计数

- 先完成问题回归，再进入付费运行。
- 先 ReAct 1 Case，再 ReAct 4 Cases，检查实际 Judge 与证据。
- 接入 TradingAgents / GPT Researcher，运行 certify 后才能标记 ready；不伪造认证。
- Case 对话从 1 轮逐步增加至 2 / 3 / 5 轮；max_steps 是上限，按实际 Input 数记录，检查同 Case 历史与跨 Case 隔离。
- 最多 200 个有效完成 Case。失败另记原因和实际请求，不算完成额度；已付费请求仍记账，未知响应先恢复查询，不能盲目重复请求。
- 多 Agent、每个 3～5 Cases 连续成功 5 轮即可提前结束。正常 Judge issue 是评测发现，不把它篡改为 pass；要求执行、证据、提交、Judge 返回与宿主验收正常。
- 外部搜索 API 配额用尽时停止受影响运行，按授权 disable ReAct 后测试其余 Agent；剩余 Agent 也需要模型和 Kuma 服务额度，不能假定完全无外部依赖。

## 状态

已完成离线回归和真实离线容器验收；真实服务验收未完成，当前因模型凭据 401 暂停。首批 test_issue10/14/31/32/36 共 17 项通过：修前 7 失败 / 10 通过，修后全部通过。现有全套离线测试 178 通过 / 6 个明确选择性验收跳过。
真实完成 Case：0；真实评测尝试：1；满足终止条件的连续轮数：0。

里程碑：`ac1b659` 保存此前并发重构和审查基线。首批修复包含控制流 span 关闭、host callback 边界、关闭 stdin、Docker 二次清理超时，以及按已记录终态验收 trace；策略、认证、转换、采集故障仍拒绝。

- `6d3f588`：首批 17 项回归已 push 至 YaoAnthony fork。
- 第二批：test_issue12/15/17/18/19/37，统一显式 --yes，拒绝确认不调用服务；evaluate 按全部 Judge 报告返回状态；viewer 路径/端口诊断与启动 flush。CLI 捕获配置异常，公开 Python run 的原异常契约保持。全套离线回归 194 通过 / 6 跳过。
- `8116e23`：第二批 CLI 修复已 push。
- 第三批：test_issue20/34 覆盖 SDK 具体错误、生成早期错误、诊断损坏、外部链接、凭据脱敏、同 Case / Run 报告校验和失败 Case 导出。报告留在 failed Case 的 artifacts 字段，不伪造成功 BenchmarkResult；终端与 viewer 提示已收报告和宿主拒绝。Python 203 通过 / 6 跳过，Web 20 通过，生产构建成功。
- `5d2eca7`：第三批已 push。
- 第四批：真实 PyPI SDK + 真实 LangChain tool 验证结构化参数、原生 ToolMessage 内容与 tool_call_id 进入官方 trace；每 Input 保存原始 capture_status。1/2/3/5 轮各跑两个独立离线 Case，验证历史延续与 Case 隔离。显式 timeout/cancelled 映射官方 timeout/aborted；SDK HTTP 选项不再硬设 max_retries=0。保留公开请求查询/恢复入口，不创建替代付费请求，不自动将恢复报告判为宿主通过。全套离线测试 223 通过 / 6 跳过。

本地原有未提交修改保留。公共 observer/runtime/CLI 的必要修复按其职责落地，Kuma 专属协议继续放 sdk/plugin/kuma。

- `36fca31`：第四批 SDK 协议修复已 push。
- 第五批：无凭据离线示例（test_issue44）、CLI / onboarding / 中英排错文档和 README 链接修正。真实 Docker 并发/取消与 PyPI SDK 验收 21 项通过；目录插件真实容器验收 1 项通过。全部是离线 Provider，不计入真实服务额度。
- 容器证据：`results/verification/kuma-pypi-5a1ff7c6735941469548901559944f32/`（Case、Agent 输出、Judge、verification.json）；同目录下 docker-concurrency-* 与 sdk-directory-* 保留其他验收。

## 真实服务阶段：首个 ReAct Case

`fe26496` 文档/离线示例里程碑已 push。全套 Python 225 通过 / 6 个 opt-in 跳过；上述容器验收均已另行实际运行。

- Case 生成成功，提交失败执行的证据后 Judge 返回 `insufficient_evidence`，原始报告保留。
- 模型请求返回 OpenRouter 401 `User not found`。使用同一 .env key 直接 GET 官方 `/api/v1/key`，仍为 401；shell 没有覆盖，未配置其他 base URL。该独立查询没有发送模型请求。
- 这是凭据/账户鉴权阻塞，不能通过改 SDK、增加重试或禁用 ReAct 解决；三个 Agent 共享该模型凭据。已暂停额外真实 Case/Judge 调用，等待用户在本地更新 key。
- Ledger 记录成功 0 / 尝试 1 / 已生成 1 / 已收 Judge 1；失败不计成功额度，但不宣称生成与 Judge 免费。实际费用由服务账单确认。
- 继续进行 TradingAgents / GPT Researcher 官方源码接入和离线验证，真实 certify 前保留 adapting。

## 新 Agent 接入记录

官方源码均下载并逐文件核对，已有上游文件未改；只在 source 中新增 ABB loader metadata，binding 与配置在外层。

| 项目 | 发现 | 处理 / 验证 |
| --- | --- | --- |
| TradingAgents callbacks | 官方 propagate 不转发工具 callbacks | binding 驱动同一 compiled graph 并显式传 RunnableConfig；边界回归检查 history / callbacks。 |
| TradingAgents 数据服务 | 默认完整分析师涉及额外服务 | 明确配置 market analyst + 原生 debate/risk 工作流，yfinance；未接 brokerage。真实原生 Yahoo 查询成功。 |
| GPT Researcher 外部依赖 | 默认 Tavily / OpenAI embeddings 需要其他凭据 | 使用官方 arXiv retriever 与固定 revision 的本地 HuggingFace embedding，范围在 profile 写明。 |
| CPU 镜像 | 默认 PyTorch 包拉入 GPU 依赖 | 中断旧构建，改官方 CPU index；断网实际向量计算通过，torch 2.14.0+cpu、384 维。 |
| arXiv 公开检索 | 原生检索和一次独立 HTTP 检查均收到 429 | 停止重试、保留未通过状态；不能把空来源报告当成功联网验证。 |
| 可选 MCP | 上游 import 打印缺 langchain_mcp_adapters 的提示 | 此配置明确 disabled，非启用能力；未伪造 MCP 工具。 |
| Registry 生命周期 | 下载源码不足以 ready；还要求 requirement.md | 补齐必需描述文件，按真实 load_registry 校验；两个新 Agent 均 adapting。 |

Issue #39：主机边界与当前镜像真实断网验收通过；后续新增真实 LangGraph 节点边界回归。两个镜像均使用 PyPI Kuma 0.2.4。
完整 artifact 目录与源文件校验数见 `Onboarding-Acceptance-2026-09-14.json`。
这些检查未创建付费 Case、未调用真实模型/Judge，也未运行 certify。

## 恢复顺序

1. 用户在本机更新 `.env` 的 OPENROUTER_API_KEY；先做官方 `/api/v1/key` 只读检查。
2. 复用首个已生成 collection（路径见 Ledger），通过 sdk-options 的 `case_collection` 执行 ReAct 1 Case。Judge 是新请求，仍可能收费。
3. 通过后生成并完整运行 ReAct 4 Cases，再实际 certify；不能把失败计成完成额度。
4. 确认 arXiv 限流解除/合适的原生检索配置后，两个新 Agent 各 evaluate、certify，凭真实结果写 ready。
5. 三个 Agent 每个 3～5 Cases，max_steps 从 1 → 2 → 3 → 5。记录生成与实际执行 Inputs 数量；上限增加不保证生成多轮，不能篡改官方 Case 补轮数。
6. 任一新故障先查 SDK 官方协议、保存请求/原始报告、回归修复并 push，再继续。达成五次连续合格多 Agent suite 且实际多轮得到验证，或累计 200 成功 Case 后停止。

仍未完成：ReAct 成功 1 Case / 4 Cases、三个 Agent 真实认证、真实多轮与五次连续并发验收。当前阻塞是模型凭据 401；arXiv 429 是新 Agent 的额外联网阻塞。

- `6437f4c`：两个新 Agent 的官方源码接入、断网依赖验收和首次真实失败记录已 push。随后复核修正新增入口 metadata，指向确实存在的上游类；GPT Researcher 通过显式单节点 LangGraph binding 接入，未将其原生 Python 类冒称为 LangGraph。增加入口定义校验和真实 LangGraph 边界回归。

最终主机回归：237 通过 / 8 opt-in 跳过；8 个 opt-in 容器检查已分别启用运行通过（Docker suite / PyPI / 目录插件 / 两个新增 Agent）。最终实际付费运行仍为 0 成功 / 1 失败，不满足真实验收完成条件。

完整 Issue 追踪表见 `Issue-Fix-Status-2026-09-14.md`；补充 test_issue8/9 证明既有 whitelist 与 endpoint 诊断边界。
