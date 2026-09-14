# Issue 修复状态与验证范围

对应 [31 个 Issue / 18 个 PR 的审查基线](Upstream-Issue-Review-2026-09-14.md)。
代码回归通过不代表真实服务最终验收完成。OpenRouter 凭据已恢复，三个 Agent 均已通过真实 certify；当前有效完成 45 / 尝试 67，五次连续合格混合 suite 尚未达成。真实运行中发现的 SDK 适配错误已补回归修复；仍收到少量远端 CaseGen / Judge 终态错误，不能在 ABB 内伪造其修复。最新计数见 [运行记录](Benchmark-Repair-Campaign.md)和 [Ledger](Benchmark-Campaign-Ledger.json)。

| Issue | 当前处理 | 验证或限制 |
| --- | --- | --- |
| #7 | 按 PyPI 0.2.4 create_run/save_case/case_path 协议生成与复用 | test_issue7；真实服务成功生成并加载首个 Case。 |
| #8 | 沿用精确 release-check whitelist，无须套用旧 PR22 | test_issue8；真实 release GET 200，其他 GitHub API 未放开。 |
| #9 | 保留 source/target host、调用 ID、HTTP 状态，去掉 query/fragment | test_issue9；不是本轮新增的 runtime 修复。 |
| #10 | GraphBubbleUp 控制流关闭 span，不作为 ERROR | test_issue10；真实 LangChain 工具参数/结果证据亦覆盖。 |
| #11 | 旧 sdk_source 路径方案已退出；插件独立 PyPI requirements | test_kuma_pypi 的安装/旧选项拒绝检查。 |
| #12 | run 支持显式 --yes | test_issue12。 |
| #13 | 使用官方有效策略坐标；当前三个 profile 显式选 Research CAND-009@1 | 先测 basic-safety-research，再依据任务适配性切到 Research；实际 CaseGen 返回坐标已核对。仍有少量超出 Agent 能力的服务生成场景，独立记入 Case-Scope-Review。 |
| #14 | 二次 Docker 清理超时不泄露 argv/密钥 | test_issue14；安全异常替换并抑制原 traceback context。 |
| #15 | evaluate 汇总所有 Judge，行为 issue 不再退出 0 | test_issue15；实际失败运行退出 1。 |
| #16 | 不恢复已淘汰的 SDK 源码 CLI 参数 | test_kuma_pypi。 |
| #17 | viewer 路径、端口、启动错误转换为明确诊断 | test_issue17。 |
| #18 | evaluate/certify 拒绝确认时不执行 | test_issue18。 |
| #19 | 配置错误在 CLI 层处理，保留 Python API 原异常契约 | test_issue19。 |
| #20 | 失败 Case 保留匹配身份的 Judge/artifact；修复官方不可变 Submission 被误判无证据 | test_issue20、test_issue20_evidence：PyPI 1/2/3/5 轮修前 4 失败、修后通过。真实复用 Case 宿主接受；三 Agent 12 个 Case 中两个远端 Judge 失败时其余十份结果仍保留。 |
| #31 | Docker 边界不注入宿主 callback 对象 | test_issue31、真实目录插件容器验收。 |
| #32 | 关闭 stdin 不抹掉已完成 execution，viewer 仍清理 | test_issue32。 |
| #34 | 原 SDK code/request ID 与相关网络错误分别展示；保留公开请求恢复入口 | test_issue34、test_issue34_recovery；真实 PyPI 终态失败账本回放覆盖三类远端错误（含 retryable=true），证明不新建网络客户端、原记录不变；真实中断成功恢复仍未做收费验收。 |
| #36 | 已记录的连接/上游终态与采集/策略等致命错误分开 | test_issue36、Docker 并发/取消验收；未从字符串猜测用户主动取消。 |
| #37 | viewer 启动信息立即 flush | test_issue37。 |
| #38 | 补评测目标、结果含义和可运行结果示例 | README、Troubleshooting、真实执行的 offline_demo。 |
| #39 | 两个上游 Agent 原源码接入；修正 profile 标题、输入默认值、模型协议、工具历史与原生联网配置 | test_issue39、实际镜像依赖/协议/egress 验收；ReAct、TradingAgents、GPT Researcher 均由真实 certify 更新 ready。 |
| #40 | Docker 前置条件与官方平台安装入口 | README；断网本地 demo 明确无需 Docker。 |
| #41 | 安装后 sdk list 验证与预期结果 | README；目录发现测试无需凭据。 |
| #42 | 说明三类凭据用途和官方入口 | README；模型 slug 不是密钥，不编造 Kuma 发放入口。 |
| #43 | KUMA_API_KEY 非空优先，DEFUZEX_API_KEY 为 ABB 别名 | test_issue43；仅记录变量名。 |
| #44 | 增加真正无账号/网络/Docker 的本地示例 | test_issue44；明确使用离线 Provider。 |
| #45 | 模板模型值不等于运行时默认 | README、中文指南。 |
| #46 | 修复翻译相对路径、补 CLI/onboarding/中文操作指南 | test_issue46 校验入口文档链接；深入设计仍以英文为准。 |
| #47 | 中文目录图改为真实目录结构 | 中文 README。 |
| #48 | 补环境、网络、证据、Judge 和失败结果排错表 | Troubleshooting、中文指南。 |
| #49 | 解释 ABB / Kuma / DefuzeX 服务职责 | 仓库文档已补；外部产品网站未修改或宣称修复。 |

文档问题通过可运行示例和链接校验覆盖，没有为每段静态文字编造一个字符串断言。
关键运行错误分别放在 test_issue 编号文件。旧 PR 涉及已删除路径和旧 SDK 合同，
采用当前架构实现与回归，不整批合入旧代码，也未向上游发送评论或合并 PR。

当前主机回归为 264 passed / 8 opt-in skipped；需要 Docker 的检查已分别显式运行，最近新增的两个 Agent 容器兼容性回归也实际通过。真实历史传递已覆盖 ReAct / GPT Researcher 的 1/2/3/5 轮与 TradingAgents 的 1/2/3 轮；后者的 5 轮仍在计划中。

仍需区分两类上游限制：CaseGen 偶尔输出超出 profile 能力的任务；Judge 偶尔返回 model_invalid_result、request_failed 或 service_busy，而 Agent 和证据提交已成功。原始 code/request/operation 身份已记录；没有自动重复计费请求，没有把这些失败计为成功额度。

补充 Issue34 定向验证：11 passed。新增的 3 个真实 PyPI 账本回归只验证已失败记录的恢复行为；不宣称修复服务端错误。SDK 公共 request summary 不暴露 error_code/error_retryable，原错误保留在 SDK 磁盘记录及 ABB manifest 中，测试遵循这个实际合同。

**11:15 验收更正：** 完整 HTTP 审查发现多轮 PubMed 查询触发 414；此前 8 个已收到 Judge 的 Case 不满足无出错验收，已从成功额度扣除，累计由 46 更正为 38。首次两 Agent 五轮批次只证明历史/证据/Judge 链路完成，不再计作完整无错混合验收。原始结果不变，完整更正见 PMC-URI-Acceptance-Correction-2026-09-14.json。修复检索传输并重新实测后才能恢复计数。

Issue39 多轮补修：原生 PMC GET 搜索完整对话引发 414，已改为检索边界分离上下文/当前问题，并支持精确 ESearch form POST。主机、真实断网顶层入口、实际拦截器和原始官方两轮 Case 均通过；中间重复 prompt_family 错误及修复也保留真实回归记录。TradingAgents 真实三轮已通过，三 Agent 五轮与五次连续合格批次仍待完成。
