# Kuma 插件修复方案（收窄范围）

状态：待实施，仅方案；未修改运行逻辑。
实施代码范围：`agentbench/sdk/plugin/kuma/`。
对齐版本：PyPI `kuma-defuzex[otel]==0.2.4`。
本方案替代此前包含 BBA 通用 runtime、observe、CLI 和 Agent binding 改动的较大方案。
上游报错复核：[2026-09-14 PR / Issue 对照](Upstream-Issue-Review-2026-09-14.md)。已按当前并发代码重新判断，不以 PR 是否合并代替本地检查。

## 原则

Kuma 适配只负责 SDK 配置、Case/Run/Input/Submission/Report 协议、SDK 证据状态读取和 SDK 请求恢复。
不把 Company 特殊输入规则、通用 LangGraph instrumentation、Docker 安全处理或 Suite 状态模型塞进 Kuma 插件；不 monkey-patch 外层模块，不重放本地日志来伪造 span。
SDK 粒度固定为：Case → Run → Input → Submission → TestReport；BBA Suite/线程调度保持原样。
每个修改的重要函数写英文 Args / Returns / 异常 / I/O / 线程与容器边界说明。

## K1. 参数与 SDK 兼容边界

修改 `benchmark.py`、`worker.py`，必要时新增插件内 `configuration.py`。

输入：BBA 插件选项；输出：经过白名单验证的官方 create_run 参数。

- 保留现有 timeout 的容器预算语义；新增明确的 sdk_request_options，内部使用 SDK 原名 timeout / operation_wait_timeout / max_retries，采用 SDK 默认值，取消无条件 max_retries=0。
- max_steps 仍是单 Case 步骤上限；generation_count/case_count 仍是独立 Case 数。
- 不再包一层“失败就重新 create_run”的自动重试；SDK 原有幂等和不可自动重试分类保持。
- artifact_case_mapping / run._case 统一封装在插件内兼容模块，注明0.2.4边界；不散布到公共Harness，不声称存在公共Case accessor。
- 更正插件中的 create_cases 等不存在的 SDK API 注释。
- 明确凭据选择：非空 KUMA_API_KEY 优先，DEFUZEX_API_KEY 是 BBA 的兼容别名；诊断只记录选中的变量名，绝不记录值（Issue #43）。
- 更正 trace_max_bytes 的参数说明：当前是 interceptor 内存转临时文件的阈值，不截断捕获内容；与 SDK 的证据大小预算分开说明。

验收：离线检查真实0.2.4接口、参数映射、非法参数拒绝、未知Case文件不进入Agent执行。

## K2. Case 生成、保存、复用

修改 `generation.py`、`worker.py`、`benchmark.py`。

输入：Agent Profile和Case数量，或保存好的Case artifact。
输出：官方原始artifact与PreparedCase集合。

- 保留 create_run → save_case → cancel；每次生成一个Case，循环组成批次。
- 每生成一个Case立刻保存；请求数、已生成数、整批是否完整分别记录。
- 复用使用 create_run(case_path=...)，不传Profile、不重写官方内容、不调用CaseGen。
- 官方ID、顺序和artifact完整性照SDK验证；BBA摘要不代替官方核验。
- 同一个Run不并发推进，不重建SDK状态机。
- 保留当前精确 release-check GET whitelist，不因 PR22 未合并而新增必需的禁用开关或扩大网络权限。旧 sdk_source 参数不恢复，Case 来源仍以固定 PyPI 版本为准（Issues #7/#8/#11/#16）。
- Profile 预检记录所选 Strategy Group / version；需要确认服务可用性时，使用 SDK 公共 catalog 只读接口并保存实际 release，不擅自更换组。当前 ReAct 已改为 basic-safety-research@1，不能再把 BASE-05 当作现有静态配置（Issue #13）。

验收：2个Case分别生成/保存/复用，复用无CaseGen；中途失败保留之前artifact；篡改由SDK拒绝。

## K3. Input / Submission 与证据状态

修改 `runner.py`、`worker.py`。

输入：KumaInput、现有Agent调用结果、结束的真实OTel span。
输出：原始Input、映射后的Agent输入、官方Submission及逐Input诊断。

- 保留 get_input(full=True) → Agent调用 → span结束/flush → submit 的顺序。
- Agent payload及多轮方式沿用现有input binding，不在Kuma插件新增Company特殊转换。
- 对上层已明确区分的超时/中止结果映射官方 timeout/aborted；无法辨别时不从错误字符串猜测，不假装已提交。
- 每次提交后从实际history保存Submission.status、capture_status各组件及reasons、missing、dropped_count、trace_evidence与工具tool_content_status。
- 本地otel-status只表示本地导出。删除“spans非空即证据充分”的推断；SDK partial/skipped不自动改成Judge失败。
- 保持显式同进程Provider。插件的新增诊断准确显示工具正文缺失；它不能凭空补上外层没有记录的真实语义属性。

验收：真实SDK+OTel的离线步骤记录；local complete与SDK partial同时保留；root-only不声称工具完整；每Input只submit一次；最后一次submit正确取得Report。

## K4. Report 保留和 SDK 错误诊断

修改 `service.py`、`benchmark.py`、`runner.py`。

输入：官方TestReport、容器产物、宿主校验结果。
输出：保留的原报告与彼此独立的错误诊断。

- Judge状态原样保留pass / issue / insufficient_evidence。
- 宿主trace拒绝时，不删除、覆盖已有Judge报告；保存经身份/路径/结构核对的报告位置及宿主拒绝原因。
- SDK错误保留安全code/retryable/request_id等已提供字段，不把模型生成错误改成用户输入错误。
- 先读取 evaluation/manifest.json.error；生成早期失败从 evaluation/error.json 兜底，两个失败入口都覆盖。诊断读取异常不得覆盖最初异常（Issue #34 / PR35）。
- 再用现有 job/run/phase/call/request 身份关联 interceptor 的 tool_error / llm_error，兼容它们不同的来源字段。关联不足时只说明同轮相关诊断；不把最后一个网络错误武断当作原因。
- invalid_response 保留为 SDK 实际分类，同时解释关联到的代理连接故障；invalid_case_integrity 单独保留证据核查，不重签、删完整性字段或自动生成替代 Case。
- 宿主拒绝可能在 read_result 之前发生，service 的异常路径也须保留报告引用。保留产物不等于通过宿主验收；PR26 的终端提示不能替代公共结果表示（Issues #20/#36）。
- 不通过伪造成功BenchmarkResult、吞掉宿主验证异常或修改TestReport来让汇总“看起来成功”。

验收：分别模拟生成期错误、SDK invalid_response 配合连接故障、没有网络错误的 invalid_case_integrity、报告已收到但宿主拒绝。错误可区分，原始分类保留，报告仍可定位，Case仍按真实验收结果失败；损坏诊断文件不遮盖原错误。
限制：公共CaseResult模型、CLI/UI的报告显示与最终退出码不在本次范围；插件内保留产物不能宣称这些外层问题已解决。

## K5. 公开请求恢复（插件内部能力）

可新增 `request_recovery.py`，由worker提供明确恢复模式；不改公共CLI路由。

输入：原sdk-repo、client_request_id(kreq_...)、原Backend/原凭据及等待参数。
输出：官方RequestRecord，成功Judge恢复后的报告位置。

- 使用public list_requests/show_request/resume_request；HTTP request_id不作恢复ID。
- 保留原.kuma请求账本，恢复不调用create_run、不执行Agent、不重新生成Case。
- 已知operation只GET；request_not_started不自动创建替代付费请求。
- 恢复报告核对run_id/case_id；原宿主校验不跳过。
- SDK不能跨进程重建任意Run/Agent进度；CaseGen恢复不能承诺拿到可复用Case文件。

验收：模拟原请求已接受而响应丢失/轮询超时，恢复无第二次POST；报告绑定原Run；缺少恢复条件不替代新建请求。
限制：普通用户CLI如何触发恢复属于后续外层工作，不能声称仅加插件函数就完成端到端恢复体验。

## 暂不实施的外层问题与原因

| 问题 | 真正拥有该行为的模块 | 为什么不塞入Kuma插件 |
| --- | --- | --- |
| 工具结构化输入/输出和真实tool_call_id在回调处丢失 | observe/langchain.py、observe/otel/session.py | SDK无法恢复未记录的真实观测；读本地文件重造span不等价 |
| ParentCommand等正常控制流变成ERROR span | observe/langchain.py | 所有使用该框架观测的SDK都会受影响，是通用转换语义 |
| Company将整句任务放入company字段 | Agent adapter/binding/evaluation配置 | 属于Agent原生接口；不能让Kuma知道某个Agent的特殊业务规则 |
| CLI报告存在就退出0 | cli/features/evaluate.py | 是外层命令退出码逻辑 |
| trace任意错误永久拒绝、未使用已有故障分类 | runtime/interception/trace.py | 已有 ErrorCode；须同时修 sticky flag 和只认 response 的终态判定，不能仅在插件中过滤事件 |
| Docker清理超时暴露argv | runtime/docker/command.py | 是通用进程与安全诊断 |
| 宿主拒绝后汇总丢失已收到报告 | harness/result.py、结果导出/UI | 插件可保存产物，通用结果模型仍需独立支持 |
| 关闭stdin让已完成执行误报失败、viewer输出未flush | cli/execution.py、terminal_ui/presentation.py、viewer.py | 是命令会话与输出问题；不能在SDK中接管终端 |
| 通用替代SDK把host callback序列化进Docker | sdk/runtime.py、observe/host.py | 默认Kuma分支不经过此路径，属于公共观测选择边界 |

最关键的限制：仅改Kuma目录，可以修SDK接入、状态保存与恢复边界，但不能承诺修好工具正文缺失、Company输入语义或外层退出码。若后续要解决这些问题，另提对应模块的最小修复，不用插件内绕过代替。

Issue #36 的 Client disconnected 尚不能区分主动取消与网络掉线，不能从字符串映射成用户取消。Judge 无 evidence_gaps 也不证明宿主网络 trace 完整；两条证据通道分开验收。当前写盘错误已有单独的基础设施异常，不能继续把所有故障描述成完全没有分类。

## 验收与实施顺序

顺序：K4 → K1 → K2 → K3 → K5；先保留准确错误和已收到报告，再处理参数、Case、Submission及请求恢复。每项独立检查、独立可回退。
优先真实PyPI SDK的离线custom Provider、真实OTel与模拟transport；测试脚本可位于临时目录以遵守本轮目录边界，不访问付费服务。
代码实施后还需按仓库AGENTS.md完成SDK边界/plugin检查并保留真实容器Run的Case、Agent output、Submission、Judge验收产物；方案阶段不执行收费运行。

官方依据：
- https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/6808390f7fe698a096263b1c83a4c6044481b41a/docs/api-reference.zh-CN.md
- https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/6808390f7fe698a096263b1c83a4c6044481b41a/docs/runtime-trace.zh-CN.md
- https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/6808390f7fe698a096263b1c83a4c6044481b41a/docs/case-files.zh-CN.md
