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

阶段一：离线回归与真实离线容器验收通过；准备真实服务测试。首批 test_issue10/14/31/32/36 共 17 项通过：修前 7 失败 / 10 通过，修后全部通过。现有全套离线测试 178 通过 / 6 个明确选择性验收跳过。
真实完成 Case：0；真实评测尝试：0；满足终止条件的连续轮数：0。

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
