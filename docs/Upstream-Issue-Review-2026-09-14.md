# 上游 PR / Issue 与当前代码对照

> 本文是修复前的审查快照。最新处理与验证范围见 [Issue 修复状态](Issue-Fix-Status-2026-09-14.md)。

审查日期：2026-09-14。仅审查和方案更新，未修改运行逻辑。

来源：[DefuzeX-AI/AgentBehaviorBench PR](https://github.com/DefuzeX-AI/AgentBehaviorBench/pulls) 与 [Issues](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues)。本次通过 GitHub API 读取全部状态：31 个 Issue（30 open、1 closed）、18 个 PR（11 open、7 merged），以及现有评论、review 和文件 diff。逐项阅读问题与 PR 说明；大规模历史同步 PR 聚焦与 SDK、观测、结果持久化有关的 diff，没有逐行审计其所有内置 Agent 源码。

本地对照对象是 `HEAD=37f3e55c9baa35e62220aee2e19fc8f5ee4a3673` **加当前未提交改动**，包括 Case 并发重构；不是该提交的纯净版本。SDK 对照为 PyPI `kuma-defuzex[otel]==0.2.4`。原始 API 响应保存在 `/private/tmp/abb-upstream-review-20260914/`；服务端问题的复现日志来自 Issue 作者，本轮未运行收费评测。

## 先明确结果边界

当前流程是：容器保存 Input / Submission / Judge → 宿主验收 trace 和产物 → 插件返回 BenchmarkResult → Harness 汇总 → CLI 选择退出码。

这些步骤可以分别失败。因此“Judge 已返回”“宿主接受结果”“CLI 返回 0”是三个不同事实。#20、#32、#36 不能统称为“文件全部没有保存”：有的报告仍在磁盘，只是没有进入汇总；有的是提示输入异常，覆盖了命令层返回结果。

当前并发 Harness 已将普通 Case 错误保存为 CaseResult，并保留其他 Case；trace 写盘失败则另有 RuntimeInfrastructureError。旧 Issue 中一次异常导致整轮没有结果的描述，不应直接套到现在所有并发故障上。

## 用户重点关注的五个问题

| 问题 | 当前结论与准确原因 | 改动归属 |
| --- | --- | --- |
| [#10](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/10)：LangGraph 正常控制流变执行错误 | 仍在。`observe/langchain.py` 的 error callback 无差别写 span_error；`observe/otel/session.py` 标记 ERROR，`observe/service.py` 据此降级。应识别 GraphBubbleUp 控制流；不能把所有 GraphInterrupt 当成功，真正未完成的暂停仍需独立表示。 | 公共 observe；Kuma 插件不能补救已经错误记录的 span。 |
| [#14](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/14)：Docker 超时打印密钥 | 原来的常规 wait 路径已解决。现在 `DockerSession.wait()` 返回固定安全文字，attach 命令也不再携带 env。但 `runtime/docker/command.py` 的 terminate 在 kill 后裸调用第二次 wait，若仍超时，会带出 `docker create --env ...` 的原 argv。 | 公共 Docker 命令清理；应修当前遗漏，不能只照 PR25 修旧 session。 |
| [#15](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/15)：Judge 失败、evaluate 退出 0 | 仍在，离线复现。`cli/features/evaluate.py` 打印最后一个 report.status 后无条件 return 0，丢掉 execution 的失败退出码。 | CLI。注意 certify 判断的是适配完成，不等于 Judge 必须 pass。 |
| [#20](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/20)：Judge 已完成、宿主拒绝后汇总没有报告 | 仍在。`kuma/service.py` 先 validate_trace，异常会使 `benchmark.py` 的 read_result 根本无法执行；`harness/jobs.py` 只能形成不带 benchmark 的失败 CaseResult。报告文件可能仍在。PR26 也只保留位置和提示，没有恢复 Suite 的报告表示。 | 插件先保留“已收到但未验收”的报告与原因；公共 CaseResult / 导出 / UI 才能完整显示。 |
| [#36](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/36)：断流、连接中断与 trace 缺失混淆 | 仍在，但生产侧已有 ErrorCode，不能再说完全没有分类。`trace.py` 不消费这些分类，任意 llm_error 都令 `_failed=True`；idle guard 还要求每个 request 都有 response。只改 flag 仍失败。 | 公共 interception / runtime；插件可以保留诊断，不能吞掉验证异常。 |

#36 的作者记录了 87 个模型请求、82 个响应、5 个有对应请求的断流错误，但明确未确定是 Agent 主动取消还是网络断开。应表示“观察到传输终结、来源尚不确定”，不能从 `Client disconnected` 字符串推断用户取消，也不能伪造 response。Judge 的 `evidence_gaps=[]` 只描述其收到的 SDK 证据，不能证明另一条宿主网络 trace 通道完整。

修 trace 时应同时覆盖已完成响应、已观察失败终态、未知缺失和必须拒绝的策略/认证/转换/持久化故障；消费已有分类，不新增一套互相矛盾的错误字典。拒绝提示应提供安全的 code、stage、call_id 和请求终态数量，避免把存在大量配对的执行统称为“没有 matched trace”。

## 全部运行与 SDK Issue

“仍在”表示当前代码仍有该触发路径，不表示本轮真实容器运行复现了上游每一个案例。

| Issue | 当前状态 | 处理结论 |
| --- | --- | --- |
| [#7](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/7)：不存在的 generate_cases API | 已修 | PR6 已合并；当前逐个 create_run → save_case → cancel，复用 case_path。保留真实 0.2.4 合同检查，不恢复 case_batch/case_index。个别 create_cases 注释仍需纠正。 |
| [#8](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/8)：SDK release 检查被拦 | 已有替代实现 | 当前 Kuma whitelist 精确允许该 release URL 的 GET，image 将它加入评测路由。PR22 未合并不代表缺修复；不必再把禁用检查列为必修，更不扩大整个 GitHub 出口。 |
| [#9](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/9)：阻断事件缺 host | 已修，Issue 已关闭 | PR21 已合并。当前 InterceptionFailure 还提供 source/target、method、request_kind、error_code/stage。 |
| [#10](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/10)：控制流误报 | 仍在 | 见上表；公共 observe。 |
| [#11](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/11)：默认 SDK 源码目录错误 | 旧设计已替代 | 当前 image 按插件 requirements 安装 PyPI 0.2.4，不依赖宿主 sibling checkout。 |
| [#12](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/12)：run 无法跳过确认 | 仍在 | run 没有 --yes；--no-view 不能跳过最初确认。CLI 交互问题。 |
| [#13](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/13)：BASE-05 已下架 | 静态配置已修 | ReAct Profile 已是 basic-safety-research@1。当前账号是否能使用该 catalog release 仍需官方服务只读验证；不能自动替用户换组。 |
| [#14](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/14)：超时泄密 | 部分解决 | 普通执行安全；进程清理二次 wait 残余见上表。 |
| [#15](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/15)：evaluate 退出码 | 仍在 | 离线确认 Judge issue → CLI 0。 |
| [#16](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/16)：部分命令无 sdk_source | 旧设计已替代 | PyPI 插件统一版本来源；当前明确拒绝 sdk_source，不能重新移入旧参数。 |
| [#17](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/17)：view 无效路径/端口 traceback | 仍在 | 仅检查 exists，不检查 is_file；端口只解析 int；外层只捕获 ViewerUnavailable。 |
| [#18](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/18)：确认策略不统一 | 仍在 | run 有确认，evaluate/certify 提示后直接执行。属于命令交互设计。 |
| [#19](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/19)：配置报错 traceback | 部分改善 | env 加载已进入 ValueError 处理；registry 加载仍在 try 外。当前 run 已没有 --registry，旧复现命令不能照抄。 |
| [#20](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/20)：宿主拒绝后报告不可见 | 仍在 | 插件保留产物与公共汇总表示是两项工作。当前更新 run.json 已合并旧字段，不应再声称必然覆盖 service 字段。 |
| [#31](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/31)：host callback 无法序列化进容器 | 通用替代 SDK 路径仍在 | `sdk/runtime.py` 通用分支仍注入 host observer，callback 随 config 进入 json.dumps。默认 Kuma 插件提前返回，不经过该分支；不能算默认 Kuma 的调用错误。 |
| [#32](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/32)：关闭 stdin 误报运行失败 | 仍在 | post-run prompt 仅处理 EOFError/KeyboardInterrupt；OSError/RuntimeError 逃逸。viewer 会关闭，但已完成 execution 没有正常返回；不等于磁盘产物被删除。 |
| [#34](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/34)：invalid_response 隐藏连接故障 | 仍在 | 插件先只报“未完成 + 目录”。必须先显示 manifest.error，生成早期从 error.json 兜底，再补充相关 interceptor 诊断；详见下节。 |
| [#36](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/36)：断流使 trace 永久拒绝 | 仍在，分类生产侧已改善 | 写盘失败已独立升级为基础设施故障；普通 llm_error 的 sticky flag 和 idle 判定仍未修。 |
| [#37](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/37)：view 重定向时不显示 URL | 仍在 | print 未 flush，随后 serve_forever；离线模拟确认 URL 留在缓冲区。 |

## #34 的修复要求：先区分真正不同的失败

Issue 后续评论补充了两个不同案例：Company 是 ServiceError / invalid_response，且代理有连接超时；ReAct 是 CaseIntegrityError / invalid_case_integrity，代理没有网络错误。终端却给出相同的目录提示。

插件应依次处理：

1. 保存并显示 SDK 原始安全错误：phase、type、code、retryable、request_id，以及生成阶段已有的 error.json。诊断读取失败不能覆盖最初异常。
2. 按 job/run/phase/call/request 等现有身份关联网络事件；LLM 与 tool 的 source_host/source_path、host/path 字段需要分别支持。关联不充分时仅标为“同轮相关网络诊断”，不宣称最后一次网络错误就是原因。
3. 保留 invalid_response 原分类，并说明代理观察到的故障；不要伪称 SDK 返回了不同 code。mitmproxy error hook 修改 flow.response 的方案，在 Issue 作者的 A/B 实验中已无效，因为响应已经发出。
4. invalid_case_integrity 单独保留和核查原始 artifact、身份与完整性。当前证据不能定位是历史版本、服务或产物哪一方造成；不能通过重签、删字段或重新生成掩盖错误。
5. 有 Judge 报告时保留经身份、路径与结构检查的引用，分开表示 report received 与 host rejected。不要把容器写出的任意路径或文本直接拼入终端，不泄露凭据。

这属于 Kuma 插件内可以先完成的实质修复，对应方案 K4。PR35 的方向可用，但“取最后一个网络错误”的实现不宜原样搬入并发版本。

## 全部文档 Issue

| Issue | 当前状态与结论 |
| --- | --- |
| [#38](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/38)：没有评测目标/结果示例 | 仍缺清晰评测维度、Judge 输出及 viewer 示例。 |
| [#39](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/39)：生命周期与内置 Agent | 英文已补 adapting → ready，名单与 certify/Judge 区别仍缺；中文更简略。 |
| [#40](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/40)：Docker 前置条件 | 缺安装入口、平台说明。公共 runtime 有 in_process，不代表当前 Kuma 插件能无 Docker 运行。 |
| [#41](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/41)：安装验证 | `agentbench sdk list` 已能免凭据验证安装并发现 kuma，quickstart 未展示该步骤和预期输出。 |
| [#42](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/42)：密钥获取入口 | 仍缺。OPENROUTER_MODEL 是模型配置，不是第四个密钥。 |
| [#43](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/43)：KUMA / DEFUZEX key 优先级 | 未写清。worker 实际使用 `KUMA_API_KEY or DEFUZEX_API_KEY`，前者非空优先，后者是 BBA 兼容别名；只显示选中的变量名，不显示值。插件参数说明纳入 K1。 |
| [#44](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/44)：无凭据体验 | 部分成立。旧 local_sdk/case_file_sdk 示例存在，但 python:... CLI 选择方式已不适配当前目录发现。sdk list 可用，但不等于完整离线评测；仍需可运行教程或示例结果。 |
| [#45](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/45)：模型默认值歧义 | 英文部分说明，中文不足。模板预填值不是运行时默认；缺 --model 与对应 env 时仍报错，不能照 Issue 建议直接宣称可省略。 |
| [#46](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/46)：本地化文档断路 | 仍在，且中文 README 移至 docs/otherLanguages 后有相对路径失效；CLI、How To Add Agent 等旧目标已不存在。需要验证链接，不能只补翻译。 |
| [#47](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/47)：目录图实际为数据流 | 英文已分开，中文仍放在“目录结构”下；部分解决。 |
| [#48](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/48)：FAQ / 排错缺失 | 仍在；旧 Troubleshooting.md 当前不存在，不能仅补一个旧链接。 |
| [#49](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/49)：ABB / Kuma / DefuzeX 关系 | BBA 文档仍未说明宿主 Harness、评测 SDK、托管服务三者职责；本轮未验证产品网站页面。 |

## 全部 PR 的采用判断

| PR | 上游状态 | 对当前代码的意义 |
| --- | --- | --- |
| [#1](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/1) | merged | 引入持久日志和 viewer 的历史基础；不是当前并发日志实现。 |
| [#2](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/2) | merged | 引入命令注册和 certify；以实际认证语义为准，不把正文 passing suite 理解成 Judge 必须 pass。 |
| [#3](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/3) | merged | 旧 Gateway 改为透明 Interceptor，基础请求配对的来源；不恢复旧 Gateway。 |
| [#4](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/4) | merged | 大规模 SDK/Observe 同步；历史上含 Kuma/Panda、错误批量 API 和 sticky trace。后续已重构，不能整文件回填。 |
| [#5](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/5) | merged | README 视觉恢复，无 SDK 运行修复。 |
| [#6](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/6) | merged | 官方 Case API 更正已体现在当前插件，保留回归。 |
| [#21](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/21) | merged | 被拦 host 已传递，当前扩充了结构化错误。 |
| [#22](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/22) | open | 禁用 release 检查；当前精确 whitelist 已替代，不列必修。 |
| [#23](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/23) | open | 策略组更正已在本地 Profile 中；只保留配置回归与实际 catalog 验证。 |
| [#24](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/24) | open | 控制流识别需求仍适用，在公共 observer 单独修。 |
| [#25](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/25) | open | 安全超时需求适用，改动位置应转向当前 command 清理遗漏。 |
| [#26](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/26) | open | 插件保留已收报告的方向适用；补身份/路径校验和独立宿主状态，不宣称已恢复汇总。 |
| [#27](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/27) | open | 旧 sdk_source 参数不采用，已统一 PyPI。 |
| [#28](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/28) | open | --yes 与统一确认需要 CLI 独立处理。 |
| [#29](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/29) | open | 配置错误仍有遗漏；后加的 viewer flush 也需单独覆盖。 |
| [#30](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/30) | open | evaluate 退出码问题仍成立；不要改变 certify 的适配认证标准。 |
| [#33](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/33) | open | host callback 边界与关闭 stdin 是两个独立问题；前者不在默认 Kuma 分支。 |
| [#35](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/35) | open | 具体 SDK 错误应显示；采用诊断需求，补早期错误与关联规则，不直接搬旧实现。 |

这些 open PR 多为堆叠分支，Files changed 包含前置旧改动。PR29 后追加的 flush 不在 PR30 / PR33 对应 viewer diff 内。因此 PR 编号靠后不代表包含所有修复，更不能把 sdk_source、旧共享 runner 状态等一并覆盖回当前架构。

## 本轮验证与方案调整

离线调用当前真实函数，未启动 Docker、Agent 或模型服务：

- evaluate 注入 Judge issue 和内部 exit 1，CLI 实际返回 0。
- run_benchmark_session 注入已完成结果：EOFError 保留结果；OSError / RuntimeError 逃逸，viewer 仍被关闭。
- view 无效路径抛 FileNotFoundError，parser 接受端口 99999；模拟缓冲 stdout 后开始 serve_forever 时 URL 仍不可见。
- InterceptionTraceState 已有一个完整请求/响应对，再收到另一个请求对应的 llm_error，两道 guard 均拒绝；仅清除 `_failed` 后 idle guard 仍拒绝。
- 用假进程让 terminate / kill 后的两次 wait 均超时，异常文本确实带出合成 env 参数；没有读取或输出真实密钥。
- 清空环境执行 sdk list，返回 0 并发现 kuma；这只验证安装发现，不代表离线完整评测可用。

补充纠正：当前 `trace_max_bytes` 虽然名称像上限，实际传到 ResponseCapture 的 SpooledTemporaryFile，是内存转临时文件的阈值，不是 trace 内容截断限制；当前 service docstring 的 byte-limit 表述应在 K1 纠正。Kuma SDK 的证据大小预算是另一套机制，不能混为一谈。

[Kuma 修复方案](Kuma-SDK-Alignment-Plan.md) 的实施顺序调整为先 K4（诊断和报告保留），再 K1/K2/K3/K5。实现代码仍限定 `agentbench/sdk/plugin/kuma/`；公共 observe、runtime、Harness、CLI 问题在本报告中标明依赖，不暗中用插件绕过。完整验收仍需之后的真实容器 Run，本文不宣称上述真实服务故障已经修好。
