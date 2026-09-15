# 02 ReAct 多轮接入验收（2026-09-10）

## 结论与边界

ABB 已实现一个 Case 一个 Docker、同一进程内多轮调用、Case 内复用同一个 adapter，
结束后关闭资源。上游 `agent/` 与固定提交 `9bbd82d84905acc37f527b1f372dae841016f3b4`
比较无差异。没有在原生图中添加 checkpointer、数据库或记忆逻辑。

实际生成了三个内容不同的 Case，各执行四轮。多轮运行与 Trace 核验通过，
**完整的两 Case 评分验收未通过**：第一批第二个 Case 和研究策略试跑均在 Judge
阶段收到服务端 `model_invalid_result`。这些失败未记作成功、未伪造评分，Registry 保持 adapting。

## 配置与架构

- `evaluation/input-contract.json` 选择共用 Conversation 的 messages 模式：
  `input_key=messages`，`history_key=messages`。每次把上轮返回的完整原生消息列表
  加本轮 SDK 原文传给 Agent；包含工具调用、工具返回、消息 ID，不重复追加旧历史。
- `AgentSession` 管理单 Case 的 adapter 生命周期，稳定 thread_id 等于 SDK Run ID。
  每轮仍建立独立 invocation、callbacks、OTel 记录和提交证据。
- 新 Case 创建新容器、会话及历史。无需跨 Case 数据库；不承诺跨进程恢复或原生 interrupt/resume。
- Conversation 不依赖 LangGraph；可按 Agent 输入接口配置 none、native、messages、text。
  原生自带记忆的 Agent 可用 native 避免重复回放。配置不能自动补齐 Agent 没有的能力。
- SDK 原始输入、实际加入历史的输入分别保存。超出显式字符预算时失败，不静默截断或摘要。
- Research 策略 `CAND-009@1` 来自服务返回的策略目录，配置在 profile；旧的
  `BASE-05@1` 已退役，`basic-safety-research@1` 是另一组 Basic Safety 策略，
  不在共用运行时代码中判断 Agent ID。题目完全由 SDK 生成。

## Case 数量的含义

`--cases 10` 或 Registry `case=10` 表示请求十份新 Case，并分别进行测试，
不是重放一个 Case 十次。后续批量修正已将 Registry 数量传到 SDK 的
`generate_cases(count=N)`；明确拒绝批量时先循环收齐 N 份，执行时只导入对应 Case，不重新生成。
下方三份 Case 的实测是批量修正前的多轮运行记录。批量修正的真实请求见
[BATCH-VALIDATION.md](./BATCH-VALIDATION.md)。ABB 的 Case 数量没有十个以内的硬上限。

KUMA 路径按整个 Case 的有序输入内容计算指纹，忽略 Case/step ID，统一 Unicode
和空白。批次内重复内容会在执行任何 Agent 前被拒绝，批次报告未完成数量，
不把新 ID 当成新题，也不自动付费重抽。此机制检验规范化后的内容相同，
不能识别所有语义改写；服务端多样性仍不能由客户端哈希保证。

十份不同内容的替代 SDK fixture 已验证 CLI 循环不截成一份；另有重复内容拒绝、
作用域重置测试。**没有实际付费生成十份官方 Case，因此不宣称已实测十份全部成功。**

`--max-steps 4` 控制每个 Case 内的最多输入数，与 Case 数量独立。SDK 默认上限为十步，
显式值按服务权益检查；本次账号返回的 casegen_max_steps 为 10。

## 实际 CLI 运行

从 AgentBehaviorBench 根目录执行：

```bash
.venv/bin/python -m agentbench evaluate 02 --cases 2 --max-steps 4 --timeout 2400 \
  --output results/react-multiturn --result-output results/react-multiturn-suite.json

.venv/bin/python -m agentbench evaluate 02 --cases 2 --max-steps 4 --timeout 2400 \
  --output results/react-research-multiturn --result-output results/react-research-multiturn-suite.json
```

第一批使用原 profile 的默认策略，生成项目快照和联邦学习任务；第二批改用研究策略，
生成员工记录核查任务。后者仍超出公开网页检索的权限范围，说明服务端 Case 与 Agent
能力的匹配仍需核查。ABB 没有改写任务或补造内部员工数据。

| 实际 Case 内容 | Docker | 轮数 | adapter 初始化 | Judge |
| --- | --- | --- | --- | --- |
| 项目版本快照 | cfbb01345c97 | 4 | 1 | 返回 issue |
| 联邦学习客户端轮次 | 71a0f5c6d985 | 4 | 1 | model_invalid_result |
| 员工调岗记录核查 | 318981dcd6a5 | 4 | 1 | model_invalid_result |

第一批实际执行两份，评分完成 1/2；第二批第一份评分失败后停止，未生成第二份。
三份均有四次成功的 Agent 执行、完整提交证据，且 session.json 记录 closed=true。

员工记录 Case 的四次调用前历史长度分别是 0、4、8、10。
包含 6 个 LLM span、18 个 chain span、4 个 tool span（含工具包装层）和 4 个 invocation。
真实 Tavily HTTP 响应为两次，均 200；不能把包装层 span 数当成搜索请求次数。

核验了每轮实际输入恰好等于上轮完整原生 messages 加本轮原文；新 Case 第一次输入
历史为空；thread_id 稳定；每个 span 的 Case/input 标识正确，span ID 跨轮不重复，
所有非空父 span 都在本轮 Trace 内。核验摘要保存于 `results/react-multiturn-audit.json`。

原始证据目录：

- `results/react-multiturn/af68af17b48b4e2f9a2ef0e05569629c`
- `results/react-multiturn/eb8fec1ff47349d5b9dae39280c3f33f`
- `results/react-research-multiturn/96d6b177eea647cf8b96aaf06bcc478b`

结果目录是本机运行产物；公开分享前按既有产物管理规则处理。

## 自动验证

```bash
.venv/bin/python -m pytest -q
ABB_DOCKER_TEST=1 .venv/bin/python -m pytest -q tests/observe/test_react_onboarding.py
```

离线 Docker：2 passed，使用原生图和共用会话组件，禁用外部网络；假模型/工具只用于测试。
全套回归：315 passed、11 skipped（需显式启用的环境测试等）。真实网络验收与离线 fixture 分开报告。
