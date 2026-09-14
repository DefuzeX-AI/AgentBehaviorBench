# Upstream Issue / PR resolution audit — 2026-09-14

审查实现版本：fork `YaoAnthony/AgentBehaviorBench` 的 **`140eefdca4eeddc853ee3d783b09182973493828`**。本轮只审查，新增本报告；没有修改实现、替换原生 Agent 源码或调用付费 API。

最新读取 upstream `DefuzeX-AI/AgentBehaviorBench` 的全部 Issue、PR、现有普通评论及 PR diff/review。共 **40 个 Issue、18 个 PR**；比上一份 31 项审查新增 #50–58。GitHub 上只有 Issue #9 closed，其余 39 个 open；7 个 PR merged，11 个 open。PR 的 head SHA / updated_at 均与当天较早完整审查缓存一致，因此复用其文件差异和 review。

**本地结论：16 项原问题已解决，3 项由新架构消除，14 项部分解决，7 项未解决。** 上游仍 open 不等于本地未修复；本地修复也不表示上游已合并。本报告替代旧 `Issue-Fix-Status-2026-09-14.md` 中过宽的“全部修复”判断；旧运行记录仍按其实际版本保留。

状态含义：**已解决**是原始核心故障/诉求已有代码与证据支持；**架构消除**是原故障路径和配置已删除；**部分解决**是主因已修但原要求或当前相关用户路径仍有缺口；**未解决**是问题仍存在或功能尚未实现。本轮没有修复以下剩余项。

## 运行证据能证明到哪里

- 重新读取此前 3 Agent × 5 Case 的原始 `run.json`、SDK manifest、Judge report 和 session 文件：**15 Case、45 Input、15 Judge，15 次 host trace 接受、OTel complete、evidence captured、会话关闭、清理成功**。Judge 为 13 issue、1 insufficient_evidence、1 pass；进程 exit 1。实际并发峰值 3，总耗时 18 分 29 秒。详见 [真实运行记录](Live-Mixed-3x5-2026-09-14.md) 和 [官方请求/证据核查](Live-Mixed-3x5-Wire-Audit-2026-09-14.json)。
- 上述运行版本是 **`bf394a0`**，早于 Trading/GPT 原生入口修复。它证明相应版本可以完整生成、执行、提交、接收 Judge，**不能证明后来入口修改已通过真实官方复验，也不能证明 13 个行为 finding 已消失**。
- 当前实现的既有验收为 452 passed、11 optional skipped；另有原生容器专项验证。GPT 的原生 ReportStore/chat 多轮验收使用真实容器、PyPI SDK 与原生应用，但外部模型/检索及 Case/Judge 使用测试替身。见 [原生入口验收](Native-Entrypoint-Repair-2026-09-14.md)。
- 后续 Trading 官方 certify 在 Case generation 前访问 strategies 超时，36.703 秒结束，**0 Case / 0 Input / 0 Judge**；不是一份失败的 Agent 或 Judge 行为结果。见 [阻断记录](Native-Entrypoint-Live-Blocked-2026-09-14.json)。当前三个 enabled Agent 均为 **adapting**，不能引用历史 ready 记录宣称最新入口已认证。
- 本轮新增 **147 项既有定向测试通过、2 项跳过**：SDK 73/2，runtime 30，CLI 20，文档/离线 demo/归档 24；另做实际 LangGraph 路由、合法 TOML、provider 导入错误、合成凭据脱敏、真实 wheel、CLI parser 等离线探针。并未重跑 452 项全套，也没有新收费 Case。

## Issue 逐项结论：执行、SDK、CLI

| Issue | 本地结论 | 理由与当前证据 | 对应 PR |
| --- | --- | --- | --- |
| [#7](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/7) 不存在的 Case API | **已解决** | `sdk/plugin/kuma/generation.py:75` 使用 `create_run → save_case`；`worker.py:97` 用 `case_path` 复用，复用分支不再传 Profile。`test_issue7` 用真实 PyPI 本地 Provider 验证生成两个 Case、复用不重生成、中途失败保留前一个。真实 15 Case 也已走通。 | [#6](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/6) merged |
| [#8](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/8) SDK release check 被拦截 | **已解决，采用 whitelist** | `sdk/plugin/kuma/whitelist.json` 精确允许官方 releases/latest 的 GET；`image.py:60` 注入 overlay。`test_issue8` 用真实 EgressPolicy 验证允许该请求，同时拒绝 POST、GitHub /user 和其他 host。**没有禁用检查，也没有开放整个 GitHub 域名。** | [#22](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/22) open；替代实现 |
| [#9](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/9) 阻断事件缺 host | **已解决** | 代理错误事件通过 `InterceptionFailure` 保留 source/target、method、call_id，URL 去 query/fragment；`test_issue9` 通过。普通非模型阻断仍可能在终端被标作 LLM call，是另一个显示缺口，不妨碍从事件找到 host。 | [#21](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/21) merged；Issue closed |
| [#10](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/10) LangGraph 正常控制流变错误 | **部分解决** | `observe/langchain.py:29` 把 GraphBubbleUp 派生信号记作 `span_control`，OTel 正常结束。真实离线父子图路由得到 3 control / 0 error / OTel complete，不再因路由 degraded。**`observe/review.py:29,44` 仍漏识别 span_control，把这些 span 显示为 incomplete。** | [#24](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/24) open |
| [#11](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/11) 默认本地 SDK 目录错误 | **架构消除** | 镜像只从 PyPI 安装 plugin 旁的 `kuma-defuzex[otel]==0.2.4`，不再猜 sibling SDK 源码目录；Panda 旧路径也已删除。`test_kuma_pypi` 验证宿主无需安装/导入 SDK，overlay 只有 requirements。Issue 评论中的通用 wheel 路径问题另见 #53。 | [#27](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/27) open；旧方案不适用 |
| [#12](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/12) run 无法跳过确认 | **已解决** | run/certify/evaluate 均支持 `--yes`；关闭 stdin 默认拒绝执行。`test_issue12` 三命令参数测试通过。无人值守仍使用 `--no-view` 避免运行结束后的 viewer 交互。 | [#28](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/28) open |
| [#13](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/13) ReAct 使用退役 BASE-05 | **已解决** | 当前 ReAct Profile 为 `CAND-009@1`，没有 BASE-05。旧真实 3×5 的五次 ReAct 生成请求确实使用 CAND-009 并获得 Case。与 PR 的 basic-safety-research 选择不同，但解决了不可用 ID 阻止生成的问题；不代表任意未来策略或全部任务能力已验证。 | [#23](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/23) open；替代选择 |
| [#14](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/14) Docker timeout 打印含密钥 argv | **原始泄露路径已解决** | `runtime/docker/session.py:74–93` 总期限异常只含固定 `Docker Agent execution` 标签；command 清理超时也采用固定文本。`test_issue14` 与合成 argv 探针证明字符串/标准 traceback 不含值。**env 仍在进程 argv；二次清理异常的隐藏 context 仍可能持有原异常。** 正常 CLI/run.json 不读取该 context；不能扩大为所有凭据泄露路径已消除。 | [#25](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/25) open |
| [#15](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/15) Judge 非 pass 但 evaluate exit 0 | **已解决** | `cli/features/evaluate.py:92–101` 检查所有报告，任意非 pass 返回 1。除 `test_issue15`，本轮固定 execution.exit_code=0 验证 pass→0、issue/insufficient_evidence→1、[issue,pass]→1。当前 certify 判断执行适配能力，语义不等同于行为评测全部 pass。 | [#30](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/30) open |
| [#16](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/16) run/certify 无 sdk_source 参数 | **架构消除** | 已统一取消源码 SDK 配置；旧 `sdk_source` option 和 `--sdk-source` 明确拒绝，所有命令通过插件的 PyPI requirements 安装。`test_kuma_pypi::test_old_sdk_source_option_and_cli_flag_are_removed` 通过。无需恢复旧 CLI flag。 | [#27](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/27) open；旧方案不适用 |
| [#17](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/17) view 缺文件/目录/非法端口 traceback | **已解决** | 文件必须 is_file，端口必须 0–65535；view handler 捕获文件/配置错误。`test_issue17` 四组通过，输出简短诊断并非零退出。本地文件错误 exit 2，与 PR 拟用 1 不同，均满足原问题。 | [#29](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/29) open |
| [#18](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/18) certify/evaluate 未确认即执行 | **已解决** | 默认确认发生在 runner 构造及收费调用前，`--yes` 显式跳过。`test_issue18` 拒绝执行时断言 runner 根本不构造，两项通过。 | [#28](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/28) open |
| [#19](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/19) registry/env 错误直接 traceback | **部分解决** | 原始缺 env、缺/坏 registry 已有诊断且非零退出，`test_issue19` 通过。**run/certify 最初读取 env 的 try 仍未捕获 OSError，注入 PermissionError 时均向外抛出。** 当前 run 不再接受旧 --registry 参数，不能直接照抄旧命令验证。 | [#29](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/29) open |
| [#20](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/20) host 拒绝后已收到 Judge 丢失 | **已解决** | service finally → exception.artifacts → CaseResult → SuiteStore → CLI 保留匹配身份的 `received_report`，终端明确 Judge retained / Host rejected。Suite 区分 attempted、judge_received、host_accepted；`test_issue20` 和 snapshot 定向拒绝测试通过。接受数仍可为 0，已判定数为 1，未把未验证报告冒充通过。**旧名为 Issue20-Real-Acceptance 的产物实际 host 接受，拒绝分支的直接证据是故障注入测试。** | [#26](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/26) open |
| [#31](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/31) 宿主 callback 进入 Docker JSON | **已解决** | `observe/host.py:76–79` 只对 in_process 创建 HostObservation，Docker 返回 None；容器自行构造 callback。`test_issue31` 直接验证不产生宿主 callback。默认 KUMA 成功运行不能单独证明原通用 local-SDK 分支，这里以定向边界测试为依据。 | [#33](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/33) open |
| [#32](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/32) 完成后 stdin 关闭导致评测失败 | **已解决** | viewer 询问将 EOF/OSError/RuntimeError/KeyboardInterrupt 转为 quit；finally 关闭 viewer 后返回原 execution。`test_issue32` 四组验证结果对象身份不变、关闭一次。 | [#33](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/33) open |
| [#34](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/34) 连接失败只显示 invalid_response | **已解决诊断诉求** | `sdk/plugin/kuma/diagnostics.py:65–70,119–169` 先保留 SDK manifest/error.json 的原 code，再附关联网络 host/path/method/error，区分 invalid_case_integrity 和网络异常。`test_issue34` 通过，覆盖无网络错误、错误关联过滤、去敏和坏文件。**没有声称修好外部连接、篡改 SDK code 或从最后一条网络事件武断推断根因。** 符合作者最新评论及 PR35 的范围。 | [#35](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/35) open |
| [#36](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/36) 一次中断毒化整轮 trace | **部分解决** | `trace.py:85–109,159` 将已观察 transport/upstream error 记为终态；policy/auth/staging/conversion/persistence 等仍拒绝。`test_issue36` 与持久化失败测试通过。旧真实 run `74b23a3f1ee84cdab73c2c3002673247` 有 5 request / 4 response / 1 transport_error，host 接受且 Judge 已收到。**原 Expected 第4项未完整实现：异常只含计数和分类，没有首个失败 call_id/event/error。** | 无独立 PR |
| [#37](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/37) stdout 管道看不到 viewer URL | **已解决** | `cli/viewer.py:81–82` 在 serve_forever 前 print(flush=True)。`test_issue37` 使用仅 flush 后可见的缓冲 stdout，验证阻塞前 URL 已输出。 | [#29](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/29) open |

## Issue 逐项结论：文档与首次使用

| Issue | 本地结论 | 理由与剩余范围 |
| --- | --- | --- |
| [#38](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/38) 评测目标/结果示例不清楚 | **部分解决** | 英文 README 已解释执行失败与行为 finding，并提供可运行 offline demo；仍缺 viewer 截图/具体结果摘录，评测维度及中文入口说明不完整。 |
| [#39](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/39) adapting/ready/certify/内置名单未解释 | **部分解决** | README/CLI/中文 Guide 已解释生命周期并列 Agent；但 README:198–200 写三个 ready，实际 registry 均 adapting；Guide:20 与 How To Add Agent:40 的 `certify --cases 1` 被当前 parser 拒绝。**原 Issue 是文档，不是后来原生 Agent 修复或 13 个 Judge finding。** |
| [#40](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/40) Docker 安装与平台边界 | **部分解决** | 已增加官方安装链接、docker info 和离线 demo 无需 Docker 的说明；缺 Windows/WSL、Linux daemon 权限及 in_process/KUMA 容器边界的完整指引。 |
| [#41](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/41) 安装后零凭据自检 | **部分解决** | 英文安装步骤已加入 sdk list 和预期 kuma 输出，本轮清空凭据后验证 exit 0；中文 README 仍安装后立即配置 .env，未同步该步骤。本轮不是全新 venv 安装验收。 |
| [#42](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/42) API key 获取入口及使用范围 | **部分解决** | 英文 README 增加 OpenRouter/Tavily 入口、官方 Kuma key 指南和用途；中文入口、按命令/Agent 的完整矩阵与免费层说明仍不足。没有把 OPENROUTER_MODEL 错算成密钥。 |
| [#43](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/43) KUMA/DEFUZEX key 优先级 | **部分解决，功能已解决** | configuration.py:34 明确非空 KUMA_API_KEY 优先，否则 DEFUZEX_API_KEY，strip 后显式传 SDK；`test_issue43` 通过。README/Guide 说明已补，但中文 README 和 .env.example 仍只写二选一，未完整同步优先级。 |
| [#44](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/44) 没有无凭据体验 | **已解决** | `examples/offline_demo.py` 真正执行本地 Agent、本地 Judge 并生成标准结果；`test_issue44` 在无凭据独立进程验证 suite_completed / suite_passed。它不运行官方 Judge，也不自动启动 viewer。 |
| [#45](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/45) model 模板值与默认值混淆 | **部分解决** | 英文 README/中文 Guide 已明确模板是示例，运行必须提供 model；符合 providers.py 的实际校验。中文 README 仍未说明这一差别，不能宣称所有入口已一致。 |
| [#46](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/46) 本地化深层文档断路 | **部分解决** | 已有中文 Guide 和部分英文链接标签，`test_issue46` 链接存在性通过；仍有 docs/AGENTS.md 标签指向根 AGENTS.md、未统一标注英文，以及无效 certify 参数。链接存在不代表命令和翻译完整。 |
| [#47](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/47) 目录结构标题下实际是流程图 | **原始简中范围已解决** | 简中 README:119 已改真实目录树；英文 Overview 与 Repository Layout 分开。繁中译本仍有同类标题问题，不将结论扩大到全部语言。 |
| [#48](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/48) FAQ/排错与 clean 语义缺失 | **部分解决** | 已有 Troubleshooting 和独立 cleanup 文档，归档保护测试 13 项通过；排错入口仍缺 Docker daemon、401、模型名错误等逐项指南，未把 clean 范围接入该入口。 |
| [#49](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/49) ABB/KUMA/DefuzeX 产品关系 | **部分解决** | README/Guide 已解释 Harness、SDK、托管后端的职责；中文 README 本身仍简略，原要求中的官网反向说明/互链未在本轮验收，因此不能宣称整体完成。 |

## 本轮新增 Issue #50–58

| Issue | 本地结论 | 直接检查与影响 |
| --- | --- | --- |
| [#50](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/50) fresh clone 无 viewer 构建说明 | **未解决** | dist 不入 Git，README/CLI 首次使用仍缺 Node/npm 与 `npm ci && npm run build`；没有自动构建。真实缺资产 handler **exit 1 并给出提示**，作者已撤回“CLI 503”说法。开发验证文档已提 npm build，故“整个 docs 无 npm”也过时，但首次使用缺口仍在。 |
| [#51](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/51) TOML 写法影响 SDK 密钥注入 | **未解决，离线复现** | `sdk/plugin/kuma/image.py:59` 仍用精确字符串 `[runtime]\n` 替换。7 种合法 TOML 中，尾空格、注释、表名空格、引号表名、dotted key **5 种得到空容器环境**；plain/CRLF 正常。当前内置 manifest 恰好使用可匹配写法，因此旧 3×5 不能否定此 bug。 |
| [#52](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/52) 自定义 KUMA backend 不可用 | **未解决，离线复现** | overlay env_keys 不含 KUMA_BASE_URL，whitelist 只允许默认 defuzex.ai 路径。真实配置/策略探针：base URL 未转发，custom.example 不允许，默认 backend 允许。默认后端跑通不能证明支持自建后端。 |
| [#53](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/53) wheel 缺资源与项目路径错误 | **未解决，真实 wheel 复现** | 对 git archive HEAD 用官方 setuptools backend 离线构建：wheel 208 项，web/resources 各 0 项；包内 model-interceptor 39 项正常。独立解包环境导入后 viewer/.env/registry/history 均锚到 site-packages；仅临时测试文件的 clean 也进入该目录。源码 editable 能跑不等于 wheel 发布可用。 |
| [#54](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/54) redact 漏掉 token/apiKey 等别名 | **未解决，合成值复现** | `observe/store.py:28–39` 仍只按五类字段名匹配。原文 15 类键中 11 类未遮盖，包括 token、apiKey、api-key、credential、bearer、private_key。已知环境值的替换和代理的另一套脱敏能保护部分数据，但不能替代此 helper 对未知运行时凭据的保护。**未扫描/显示真实密钥，也没有证明发生真实泄露。** |
| [#55](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/55) 旧 defuzex 包/API 没迁移 | **架构消除** | `sdk/defuzex.py`、旧 optional extra 和该 SDK 导入路径均不存在；SDK/runner 不再向 create_run 传 max_inputs/requirement_path，使用当前 max_steps/agent_profile_path/case_path。registry/session 中仍有 requirement_path 作为 BBA 文件元数据，未当成旧 SDK 参数发送，不能仅凭这个词判断旧 bug 仍在。 |
| [#56](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/56) ImportError 漏出安装提示保护 | **部分解决，旧路径已删但同类缺口存在** | 原 defuzex wrapper 已删除；`sdk/discovery.py:84–95` 会把导入失败转 ProviderSelectionError。但 `sdk/runtime.py:47–56` 构造插件 runner 只捕获 ModuleNotFoundError，合法插件在工厂内抛 ImportError 时仍原样逃出，本轮离线注入已复现。不能称当前所有 SDK 导入错误都规范化。 |
| [#57](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/57) provider/framework 自动插件发现缺失 | **未实现** | 无所提 model_providers/adapters entry-point group，默认 provider/adapter 仍显式构造。Python 可手动注入 StaticModelTargetProvider，native-service 也能运行原生 API，因此这是一项配置/自动发现扩展缺口，不能解读为所有其他 Agent 都不能运行。 |
| [#58](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/58) display_path 算错根目录 | **未解决，直接复现** | `terminal_ui/presentation.py:244` 的 parents[2] 得到 `<repo>/agentbench`；真实资源目录无法 relative_to，输出完整绝对路径。影响终端展示，未影响 Case 或 Judge。 |

## 全部 18 个 PR

本表判断每个 PR 自身的主要目标。#22–33 中多数为 stacked PR，其 diff 含前置提交；不将每个累计 diff 当作一组全新的问题，也未机械合并旧目录下的补丁。

| PR | 上游状态 | 当前 fork 的对应情况 |
| --- | --- | --- |
| [#1 persistent benchmark trace viewer](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/1) | merged | 核心持久化结果/viewer 能力保留，当前改为原子 JSON/Suite 产物。首次 clone 和 wheel 的 viewer 可用性仍受 #50/#53 影响。 |
| [#2 registry-driven CLI certification](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/2) | merged | registry、certify、状态过滤仍存在；certify 现判断执行适配完整性，不要求 Judge 全部 pass。当前 adapting 是再认证状态，不能用 PR 已合并宣称 ready。 |
| [#3 transparent model interceptor](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/3) | merged | 透明拦截、替换真实 provider、保存网络证据的核心能力保留，旧 3×5 的 230 次模型请求均记录响应。#36/#54 等剩余问题分别记录。 |
| [#4 Sync local implementation](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/4) | merged | 历史大同步已进入主线，Observe/CLI/plugin 能力继续存在但重构过；旧 Panda 与旧入口已删除。它不是可整体判为“所有 bug 修好”的专项修复 PR。 |
| [#5 Restore README visual identity](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/5) | merged | 标题图、架构图、语言导航、badges 保留，迁移后相对路径检查通过；未重新做浏览器像素对比。它不解决后来 #38–49 的全部文案问题。 |
| [#6 Fix KUMA SDK Case API](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/6) | merged | #7 核心目标已实现，当前 PyPI/Case 文件调用验证通过。 |
| [#21 Carry blocked host](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/21) | merged | #9 核心目标已实现，结构化错误仍带目标信息。 |
| [#22 Disable SDK release check](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/22) | open | #8 由精确 whitelist 解决。**没有采用禁用环境变量**，本地不需要为了消除同一故障照搬这个 PR。 |
| [#23 Published strategy group](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/23) | open | #13 已通过 CAND-009 解决；PR 选 basic-safety-research，两者不是同一个策略选择。 |
| [#24 LangGraph routing signals](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/24) | open | 核心错误降级已修；span_control 在 review 中仍显示 incomplete，不能宣称整个展示链路已完成。 |
| [#25 Timeout argv disclosure](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/25) | open | 原 CLI/run.json 泄露已用固定错误文本解决。未逐字采用 PR 的全部异常对象清理策略；隐藏 context/进程 argv 边界见 #14。 |
| [#26 Retain Judge on host rejection](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/26) | open | 已实现，且扩展至 Case/Suite/CLI 和 judge_received/host_accepted 分离，证据为定向拒绝测试。 |
| [#27 sdk_source defaults/flags](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/27) | open | 被 PyPI 插件设计替代；本地已取消这个配置，不应重新引入源码目录猜测和旧 flag。 |
| [#28 Shared confirmation contract](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/28) | open | #12/#18 的用户行为目标已实现，默认确认、yes 跳过、关闭 stdin 拒绝。实现位置与 PR 不完全相同。 |
| [#29 Configuration errors / viewer UX](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/29) | open | **部分实现**：#17/#37 完成，#19 原始缺文件复现完成，但最初 env 读取漏 OSError。 |
| [#30 evaluate follows Judge](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/30) | open | #15 目标已实现，逐 Case 判定；任何非 pass 均非零退出。 |
| [#33 Host observation / closed console](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/33) | open | #31/#32 两个边界目标已实现：宿主 callback 不跨 Docker，关闭 console 不改写已有执行结果。 |
| [#35 Surface container failure reason](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/35) | open | #34 诊断目标已实现，先 SDK 原错误，再关联网络证据；没有把诊断改进描述为外部网络或 SDK 服务已修好。 |

## 本轮检查记录与剩余项

三组分工审计记录、公开 GitHub API 快照、临时 SDK 探针脚本/JSON、原始 live 产物复核汇总保存在本地 `results/verification/upstream-status-review-2026-09-14/`。这些原始资料保留本地，本报告提供可推送的结论与复现摘要。

定向测试命令分别覆盖 `test_issue7/8/34/34_recovery`、`test_kuma_pypi`、`test_sdk_directory`；`test_issue9/10/14/20/20_evidence/31/36` 与 6 项 snapshot/timeout/persistence 测试；`test_issue12/15/17/18/19/32/37`；`test_issue43/44/46` 与 `test_history_references`。147 passed 不表示 147 个 GitHub 问题已修复。

特别需要保留的未解决问题是 **#50/#51/#52/#53/#54/#57/#58**。部分解决项为 **#10/#19/#36/#38/#39/#40/#41/#42/#43/#45/#46/#48/#49/#56**。它们均只做记录；没有修改实现、伪造 readiness、改判官方 Judge、关闭 upstream Issue 或合并 upstream PR。
