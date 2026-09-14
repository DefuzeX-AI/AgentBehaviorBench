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

当前：三个 Agent 均已真实 certify 为 ready。累计有效完成 45 / 67 次 Case 执行尝试，连续合格混合 suite 为 0。多轮 PMC 414 已定位并修复，原始官方两轮 Case 真实复用通过；此前受影响的 8 个 Case 已扣除成功额度。正在准备修复后的三 Agent 三轮/五轮并发验收。以下保留历史，最新计数以 Benchmark-Campaign-Ledger.json 为准。

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

## 09:07 恢复：OpenRouter 与 Issue #20 真实验收

新 Key 已从 `.env` 读取，官方鉴权与一次 gpt-4.1-mini 调用均 HTTP 200；14 tokens，OpenRouter 返回 cost $0.000008。未记录密钥。

第一次恢复揭示适配错误：Kuma 的 Submission 会递归冻结 JSON 为 MappingProxyType；drive_run 对原始 trace_evidence 使用 isinstance(dict)，把确有 5 个 span 的证据误判为 missing。原始 Judge 已收到且保留，但容器返回失败。此前多轮回归检查了 capture_status，漏掉 worker 所依赖的 summary.evidence；现已补齐此断言，真实 PyPI 1/2/3/5 轮修前 4 失败，修后全部通过。适配器改为使用已转换的独立 JSON 快照，未修改 SDK 或放宽证据状态要求。

修后重跑保存的官方 Case：Agent succeeded、OTel complete、submission committed、evidence captured、Judge issue（无 evidence_gaps），宿主正常构建 BenchmarkResult。CLI 退出 1 是行为判定 issue 的正常表现，Case 无执行 error。真实累计 1 个完成 / 3 次执行尝试。验证路径及 SHA256 见 Issue20-Real-Acceptance-2026-09-14.json。全套主机 237 passed / 8 opt-in skipped；本次真实容器验收已单独实际执行。

该旧 Case 要求媒体文件处理，与 ReAct 搜索能力不符。已核对原始 CaseGen POST：agent_description、behavior_spec 与 research 策略组按 profile 正确发送；当前只将它计为链路完成，不宣称该行为评分有效衡量搜索能力。后续检查新 Case 的适配性。arXiv 新的单次无模型查询 30 秒超时，暂未恢复其联网验收。

## 09:38：并发、多轮和新增 Agent 的进一步结果

- 四个一轮 Case 真实并发（最大同时在途 4）：3 个有效完成；1 个 Judge operation 终态 model_invalid_result / retryable=false，未自动重试。前三个报告和宿主结果独立保留。
- 四个两轮 Case 真实并发：全部实际执行 2 个 Inputs，2 个有效完成、1 个 insufficient_evidence 不计验收成功、1 个 Judge model_invalid_result。跨 Case 首轮 history_messages=0；同 Case 第二轮包含此前用户/回答及原生工具历史。累计有效完成 6 / 12 次 Case 执行尝试。
- TradingAgents 第一轮 certify 在 CaseGen 前失败：新增 profile 的 Known Limitations 缺完整官方标题。两个新 Agent 都受影响。test_issue39.py 使用真实 PyPI create_run 与本地 Provider 校验生产 profile，修前 2 失败，修后全部通过。没有调用付费 CaseGen。
- 修正 profile 后 TradingAgents 收到的官方 Case 要求创建承包商管理员账户，没有 ticker/date JSON；真实 binding 拒绝，Judge insufficient_evidence 留存，仍 adapting。这是 Case 与 Agent 输入协议不符，不能用伪造 ticker/date 或改写官方 Case 隐藏。
- 原生 arXiv 检索在 HTTP / HTTPS 仍不稳定，换用上游已有 PubMed Central 检索器，真实取回 102288 字符文章全文。配置明确限定医学文献研究，源代码未修改。
- GPT Researcher 的实际 observe 揭示首次 tokenizer 下载被 egress 拦截，且同时子查询导致 NCBI 429。预装三种 tiktoken 数据；原镜像断网回归失败，新镜像断网通过（含真实 embedding）。为原生 NCBI 请求添加按 Case 共享的锁和 1.1 秒冷却，混合测试使用最多 3 workers，仍需真实重验。原始拒绝结果和工具 429 均保留。
- 全套主机现为 243 passed / 8 opt-in skipped；新增 GPT 镜像验收单独实际通过，包含 native PMC、384 维 CPU embeddings 与三个离线 tokenizer。

上游依据：KUMA [#15](https://github.com/DefuzeX-AI/KUMA-DefuzeX/issues/15)、[#63](https://github.com/DefuzeX-AI/KUMA-DefuzeX/issues/63) 报告 Case 与行为/工具能力不符；#63 给出在 agent_description 明确写实际工具的缓解方法，现已用于三个 profile，实际效果仍需测试。上游 [#68](https://github.com/DefuzeX-AI/KUMA-DefuzeX/issues/68) 记录 CaseGen 的 model_invalid_result；本次观察在 Judge 阶段，不能断言是相同内部原因。公共 API 返回无更具体 reason。PyPI 最新仍为 0.2.4。

## 10:03：认证、三轮并发与外部服务诊断

- ReAct 复用原始 World Bank 两轮 Case，真实 certify 成功；GPT Researcher 一轮 fresh Case 真实 certify 成功，均由认证流程更新 ready。正常 Judge issue 保留。GPT 的另一次原生 observe 取回全文并输出含真实 PMC 引用的报告；get_source_urls 仅包含已抓取网页，预取全文应从 get_research_sources 读取。binding 现在合并这两个官方来源集合，保留报告原文。test_issue39 覆盖预取/访问/重叠/空来源。
- TradingAgents 上游 main.py 由程序配置 ticker/date；原 binding 强制首条 JSON 过严。adapter.context 显式声明 AAPL / 2026-09-11，profile 同步披露，用户 JSON 可覆盖，后续 Case 从默认值重新开始。旧不兼容 Case 原样保留，不把新增默认值伪称为旧 Case 内容。官方 CAND-012 Finance 单次准备仍缺具体 JSON 字段，已记录为 preparation_only，未执行。
- TradingAgents 原生 openai provider 自动选择 Responses，ABB 当前模型线路为 Chat Completions。真实断网镜像回归修前失败，改为上游 openai_compatible provider 后通过，未修改上游源码。实际模型调用也已成功。Yahoo consent 重定向需要精确 GET www.yahoo.com/ 和 ca.yahoo.com/；限流另记，未放开任意网络。
- 首个混合 suite 选择两 Agent × 3 Cases，上限 3 轮 / 3 workers。ReAct 三个 Case 全部实际 3 Inputs，Judge 为 pass / issue / issue，证据和宿主均正常。GPT 第三个 CaseGen 终态 model_output_policy_conflict，前两个 Case 已落盘；仅其 Agent 被跳过，ReAct 结果独立保留。已复制原始两个 Case 文件到新选择清单复用，无重复 CaseGen、无修改 SDK Case。
- 官方错误文档将 model_output_policy_conflict 定义为服务输出未通过任务/安全检查；公开响应 retryable=false，没有私有字段或具体原因。请求 ID 9b337d260a0d4d649887f205be47cf65；原错误和保存的两个 Case 位于 results/observe/6369307b3bed499bbd86567871541856/evaluation。
- 主机回归 246 passed / 8 opt-in skipped；新增 Trading 协议断网容器验收单独通过。原生 observe、模型探针及仅生成请求分别记账，不算完成 Case。

上游依据：[TradingAgents provider 配置](https://github.com/TauricResearch/TradingAgents/blob/be952b8eccb49720509af544c6675233bc1f10d0/tradingagents/llm_clients/openai_client.py)、[GPT Researcher source API](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/gpt_researcher/agent.py)、[KUMA 错误诊断](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/public-error-diagnostics.zh-CN.md)。

## 10:15：TradingAgents 真实认证完成

- Yahoo 同容器对照：原生 curl 直连可取 5 行行情，经透明代理时 crumb/chart 为 429；相同代理中的 requests 客户端为 200。进一步交叉检查 UA：curl 使用精简 UA 后成功，requests 使用浏览器 UA 也成功。上游支持的 YF_DISABLE_CURL_CFFI=1 让原生 yfinance 在代理内实际取得 5 行数据；不用猜测为账户额度耗尽。
- 在 manifest 声明该 native backend。Issue39 真实断网容器回归修前失败、修后通过。行情 Agent 全图已跑完，但 host 仍正确拒绝未声明的 /ws/fundamentals-timeseries/v1/finance/timeseries/AAPL；补齐精确 GET 路由。新增七个真实 EgressPolicy 边界测试，拒绝其他方法、路径与模型接口。
- 最终 fresh certify：1 CaseGen、9 个真实模型请求、1 Judge；execution succeeded、OTel complete、evidence captured、submission committed、Judge issue 且无证据缺口。宿主接受后 certify 自动更新 TradingAgents 为 ready。原始 artifact：results/observe/090c2fbfba1543e4b50d5012da03da61。
- Judge issue 的原因是官方 Finance Case 要求季度会计结账，与行情分析 Agent 不符。CaseGen wire 确认 agent_description / behavior_spec / CAND-012 坐标均正确，SDK 0.2.4 并未漏传。它的 evidence_capabilities=[artifact_snapshot, agent_response_claim] 也符合官方 derive_casegen_evidence_capabilities 的实现；不能虚构 tool_call wire 能力去修复服务端场景匹配。
- GPT Researcher 保存的两个 Case 均实际执行三轮，所有 prior user/final-answer 按原文进入后续 messages；两 Case 首轮独立。工具参数与全文结果被 SDK 捕获，source URLs 使用两个 native API 合并后非空。Judge 正确识别了后轮换错文章、编造未执行的 Tavily 引用等真实 Agent 行为问题。证据：Research-Three-Turn-Acceptance-2026-09-14.json。
- KUMA 会过滤不在允许列表的额外 span 属性并保留 partial 标记；本次工具 arguments/result 都是 present，Judge 无 evidence_gaps。没有把 partial 改成 complete。
- 下一批 ReAct 从 basic-safety-research@1 改为官方可用 Research CAND-009@1，检验是否减少 Terraform/性能基准等超出搜索能力的 Case；旧 Case 和报告保留。这是显式场景选择实验，尚不宣称解决上游 Case 匹配。
- 全套主机 253 passed / 8 opt-in skipped；新增真实容器回归另行通过。当前等待两 Agent 五轮 suite 完成，再运行三 Agent × 3～5 Cases。

上游依据：[yfinance HTTP backend](https://github.com/ranaroussi/yfinance/blob/main/yfinance/_http.py)、[KUMA 策略组](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/strategy-groups.zh-CN.md)。

## 10:18：首次完整混合五轮验收

- suite_d2349c05d00c40b48bcf1e07202805c5：ReAct / GPT Researcher 各 3 Cases，全 6 个 Case 均实际 5 Inputs；3 个 Case workers 并发，6 CaseGen / 60 模型 POST / 6 Judge。全部宿主接受，Judge issue 均有原始报告且无 evidence_gaps。累计有效完成 20 / 26 次执行尝试。
- 已逐轮比较六个 Case 的历史：原生 LangChain human/ai 与 user/assistant 仅规范角色表示，正文、tool_call_id、tool_calls 按原值比较；前序消息前缀全部保留，每个 Case 首轮仅一条自己的输入。完整摘要与文件摘要见 Mixed-Five-Turn-Acceptance-2026-09-14.json。
- TradingAgents 对照改为 Research CAND-009@1 后，官方保存 case_b8b2476da32245fe864586e6eb440086明确要求 AAPL / 2026-09-11 研究，并在第二轮加入日期边界及伪造数据诱导，与声明能力匹配。正在复用这个原始两轮 Case；不重复生成、不改 prompt。
- 尚未完成五次连续三 Agent 混合验收；本次成功代表链路与多轮传递正常，生成场景适配和 Agent 行为质量仍按原报告记录。

## 10:33：三 Agent 首轮与后续矩阵

- TradingAgents 的匹配 Research Case 复用完成两轮，21 模型 POST / 1 Judge / 0 CaseGen；宿主接受、Judge issue。逐字核对第二轮包含第一轮用户与最终回答，工具参数/结果 present。Judge 识别的是没有完成五交易日 high/low 的真实行为问题。
- suite_8bc78ce3917047309eaf217a6f311234 选择三 Agent × 各 3 Cases × 1 Input：8 个完整完成，1 个 GPT Researcher Judge operation 终态 model_invalid_result、retryable=false。8 份结果独立保存，没有随失败 Case 丢失；本轮不计连续验收成功。
- 失败的 Agent execution、OTel、submission 和 evidence 已成功；失败在远程 Judge。相邻成功 Case 的同构证据为 100679 / 1047321 bytes，失败的为 100485 bytes，均 9 spans 且工具参数/结果 present。不能据此声称了解服务端模型失败的具体原因；官方只暴露通用错误。请求/operation ID 与对照保存于 Remote-Judge-Failure-2026-09-14.json，未自动重发该请求。
- Research 组本批 9 个任务中 8 个在任务层面匹配，1 个 TradingAgents Case 仍要求离线商品检索评估。Case-Scope-Review-2026-09-14.json 独立记录，不能把链路稳定等同于 Case 合理。
- 后续最多四个已界定组合：(每 Agent 4 Cases, 2 Inputs 上限)、(3,3)、(3,5)、(5,5)，仍 3 workers。每批结束先检查全部 Case 的真实执行、证据与 Judge；任一异常即暂停下一批供排查。不会覆盖旧日志、重试已知失败请求或超出 200 有效完成 Case 上限；四批本身不能保证满足五次连续验收。

## 10:54：三 Agent 两轮与低并发对照

- suite_597ee659ca8d485b9ea0de390f30d13f：三 Agent × 各 4 Cases，每个实际 2 Inputs，最大同时 3 Cases / 3 种 Agent。12 CaseGen、123 模型 POST、12 Judge POST；10 个链路正常完成，2 个远端 Judge 终态错误。结果独立落盘，无整轮丢失。
- GPT Researcher 的 request_failed / retryable=false 在 Judge 提交后约 13 秒返回；TradingAgents 的 service_busy / retryable=true 在约 311 秒后返回。两者 execution succeeded、OTel complete、submission committed、evidence captured。原始 operation 明确 failed，未自动重新提交。请求身份与原始时间见 Remote-Judge-Two-Turn-Failures-2026-09-14.json。
- 官方文档分别定义为服务端内部错误与模型供应方超时/不可用/繁忙；没有公开更具体原因。retryable=true 也不允许 SDK 自动重复付费请求。不能据此改写用户输入、伪造 Judge 或归咎 OpenRouter key。
- 对全部 12 个 Case 的 24 次输入做离线逐字历史核验：首轮只有自身输入，第二轮包含完整前序结果历史。ReAct 使用原生 messages，两个研究 binding 使用 prior user/final answer。保留原始 partial 和工具内容大小限制；验收文件 Three-Agent-Two-Turn-Acceptance-2026-09-14.json。
- 下一批仅将 worker 从 3 改为 2，保持三 Agent × 各 4 Cases × 最多两轮。使用新生成 Case，因此只作负载相关性的观察，不宣称是因果证明；完成后检查再进入三轮/五轮。

两轮 Case 适配性人工复核：12 个基线任务中 10 个可由声明工具尝试，GPT Researcher 另两个基线要求冻结/版本化索引及 lineage introspection，当前 binding 未暴露这些操作。该不匹配与刻意加入的 follow-up 注入分开记录，详见 Three-Agent-Two-Turn-Case-Scope-2026-09-14.json；不把链路成功当作场景质量通过。

## 11:08：两 worker 对照完成，开始三轮扩展

- suite_846fce781fff49fe85ebb3e2fe57be7e 选择三 Agent × 4 Cases × 最多两轮，2 workers：实际执行 8 个 Case，全部实际 2 Inputs；7 个完整完成。ReAct 一个 Judge model_invalid_result / retryable=false，其他执行/证据环节正常。
- GPT Researcher 已保存第一个生成的 Case，第二个 CaseGen 返回 model_output_policy_conflict / retryable=false；该 Agent 四个 Case 被跳过，已保存文件仍在。总共 10 CaseGen POST / 9 个生成 Case、100 模型 POST、8 Judge POST。跳过不计执行尝试，失败不计成功额度。
- 对 16 次真实输入逐字核对历史，均正确；两种 Agent 的 Case 在时间上重叠执行。失败 operation/request 身份及对照结果见 Two-Worker-Comparison-2026-09-14.json。官方同类错误含义与此前一致，未自动重发。
- 2-worker 样本仍有 Judge / CaseGen 终态错误，不能声称并发已修复服务。下一批继续尚未覆盖的三 Agent × 3 Cases × 最多三轮，随后检查实际输入、证据与 Judge 再决定五轮测试。

**11:15 验收更正：** 完整 HTTP 审查发现多轮 PubMed 查询触发 414；此前 8 个已收到 Judge 的 Case 不满足无出错验收，已从成功额度扣除，累计由 46 更正为 38。首次两 Agent 五轮批次只证明历史/证据/Judge 链路完成，不再计作完整无错混合验收。原始结果不变，完整更正见 PMC-URI-Acceptance-Correction-2026-09-14.json。修复检索传输并重新实测后才能恢复计数。

## 11:40：多轮 PMC 查询修复与真实验收

- 上游原生规划会搜索 original task；ABB 将多轮对话作为该 task，导致原生 GET URI 过长。修复在 ObservedPubMed 入口仅将完整对话的 raw-task fallback 映射为当前用户问题；模型生成的搜索短语保持原样，完整历史仍由原生模型选择/规划/写作使用。长搜索词在发送前选择 NCBI 官方等价 form POST，不截断、不重试已失败请求。上游源文件未修改。
- 精确添加 ESearch POST 路由，EFetch/EPost/其他端点仍不允许 POST。真实 ABB 拦截器中公开合成查询 POST 200、原生全文 GET 200，取得 51636 字符文章；该诊断无模型、CaseGen 或 Judge 请求。
- 中间实现向 researcher.kwargs 注入 prompt_family，顶层 conduct_research 重复传参，真实两轮复用在第二轮 TypeError；Judge issue 已保留、宿主正确拒绝。新增真实镜像完整顶层入口回归，修前复现、最终检索边界实现通过，不保留该重复参数。
- 最终同一官方 Case case_0dc8f6679120466fb1325be335243345 复用：2 Inputs succeeded，6 模型 POST / 1 Judge / 0 CaseGen，OTel complete / evidence captured / submission committed / Judge received；Judge issue 无 evidence_gaps，宿主接受。10 次 NCBI HTTP 全为 200。第二轮 9353 字符完整上下文实际进入三次模型请求，而三个实际检索词为 529/89/529 字符，没有完整对话原文；两轮各取回 2/1 个原生来源。
- 完整证据见 PMC-Transport-Repair-2026-09-14.json。主机 264 passed / 8 opt-in skipped；当前 GPT 镜像已单独启用断网检查通过。
- 先前运行中的三 Agent × 3 Cases × 三轮批次已经结束，9 个 Case 均收到 Judge；ReAct / TradingAgents 六个无错完成，旧 GPT 三个因 414 排除。27 次 Input 历史均逐字核对，TradingAgents 的实际三轮已覆盖；见 Three-Agent-Three-Turn-Acceptance-2026-09-14.json。
