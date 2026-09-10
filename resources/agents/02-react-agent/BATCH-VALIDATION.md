# Case 数量贯通与预生成验收

## 最终行为

Registry `case=N` 是默认数量；显式 `evaluate --cases N` 才覆盖。
ABB 先请求 SDK `generate_cases(count=N)`。如果服务明确拒绝批量，SDK 将已知的
count=1 限制映射为 `case_batch_unsupported`，ABB 才进入用户授权的兼容循环，
调用 N 次 `generate_cases(count=1)`。普通参数错误、额度、超时不会触发此降级。

**先收齐、校验，再执行**。题目不足、超量、重复 ID 或规范化后内容重复都失败，
不把一题重复执行凑数，不自动重抽替换。语义改写不属于哈希去重保证。
中途生成失败时保留已经生成的记录，不启动 Agent。

准备容器只调用 SDK，不加载 Agent，也不要求 Agent LLM trace。实际执行仍然
每 Case 一个独立 Docker，保留现有 LLM trace 验收和 Case 内多轮历史机制。

每份原始 Backend batch 都保留，`case-collection.json` 的 entries 只引用
batch_index/case_index。兼容循环得到的不同 batch_id 不会被伪造成一个签名批次。
执行时调用 `create_run(case_batch=原始批次, case_index=原始索引)`，不再次生成。
SDK 仍验证仓库指纹、策略、批次关联、签名元数据和所有步骤；不走自定义 Provider
伪装官方 Case 的旁路，也没有复制 wangyi 的策略校验 monkey patch。

已保存集合可通过现有 `--sdk-options` 提供：

```json
{"case_collection":"/absolute/path/to/case-collection.json"}
```

数量必须匹配本次 Registry/CLI 数量。ABB 保存独立导入快照，原始集合不修改。

## 真实服务证据（2026-09-10）

- 最初 `count=2, max_steps=2` 请求得到 HTTP 400 `invalid_request`，原始细节：
  `Async Case generation currently requires count=1.`
- 加入兼容后，实际请求顺序为 count=2（拒绝）、count=1、count=1。
- 收到两个不同 Case，均为两轮：依赖锁文件可复现性检查、SaaS MSA 合同准备。
- 第一轮收齐后暴露准备阶段错误要求 LLM trace，已修复；保留原始失败记录。
  后续使用这两份已保存 Case 验证导入执行，不重复出题。

原始目录：

- 拒绝批量：`results/react-batch/58230523ac6b42e6a94f99d400044810`
- 兼容收齐：`results/react-batch-fallback/c83631430d824c8f8ccd284205f5b702`
- 导入执行：`results/react-collected-execution/`

## wangyi 的 10 个 Case 是怎么来的

查阅 `wangyi/tools/case_gen.py`：`-n` 默认 10（第 185 行），通过第 143 行的
range 展开 N 个 Job；每个 Job 在第 160 行调用共享生成函数，最终调用
`provider.generate_case(ctx)`（`wangyi/tools/shared.py` 第 393 行附近）。
所以是 N 次单题生成，不是一个请求返回 N 条。

另外做了：

- 逐份落盘；跳过已有可解析的题目；`--topup` 补齐数量。
- 有限重试、可选线程并发、运行锁隔离、用量变化及任务台账。
- 旧版显式策略组路径中替换 `_selected_strategy`，绕过请求组与成员策略回显的
  两段比较。这是策略兼容处理，不是放开生成数量。
- 重试前删除 scratch 下 SDK 账本。ABB 没有复制这种恢复策略，保留 SDK 的幂等与请求记录。

本机 ReAct `039_langchain-ai__react-agent/suites/auto/cases` 和 `sg/cases`
各有 10 个 Case 文件；分别核验，均为 10 个不同 ID、10 份不同输入内容。
其历史报告 `FINDINGS-generated-cases-replay.md` 还明确记录：旧 SDK 缺少预生成
官方 Case 导入入口，导致“生成了语料”不等于“已经能按原官方身份执行评分”。
本次 SDK 新增导入入口正是为补齐这段生命周期。

旧策略目录 fixture 中确有 `max_count: 5`（SDK `tests/test_strategy_groups.py`
的 legacy_catalog_payload），但这是旧目录测试数据；当前 v2 异步端点的真实响应
仍是 count=1 限制。不能据旧 fixture 宣称当前服务支持一次五份。

## 导入执行结果

两份预生成 Case 均成功完成各两轮，使用不同容器；各容器只初始化一次 adapter，
结束后 closed=true。核验后续输入包含此前完整消息，OTel 父子关系和 Case/input
标识正确。执行阶段的网络记录中 **Case generation POST 为 0**。

| Case | 容器 | Agent 执行 | Judge |
| --- | --- | --- | --- |
| case_5efa27b9106748818260f82da5989f31 | e73364e69673 | 2/2 轮完成 | 返回 issue |
| case_35ad4032cfb54e409e7ea1573aaa8851 | 5ca06c4327b1 | 2/2 轮完成 | model_invalid_result |

所以收集与执行链路通过，完整评分仍为 1/2，不能称为 Agent 认证通过。
机器可读审计：`results/react-batch-audit.json`。没有额外实际生成十份收费 Case；
十份数量贯通由 SDK 单次 POST count=10、ABB 单次/兼容循环及导入的离线回归覆盖。

最终回归：ABB 329 passed、11 skipped；SDK unittest 551 项（1 skipped，其余通过）；
SDK Ruff 检查与格式检查通过。后端未修改，上游 ReAct 源码未修改。
