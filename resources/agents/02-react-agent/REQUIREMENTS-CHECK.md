# 多轮评测与 Case 生成需求核对

本次核对范围：本会话约定的 Case 数量、批量/临时 loop、先生成后执行、02 原版
ReAct 接入、多轮历史、Trace、CLI 验收与配置复用。后端不修改。

## 已实现并有验证证据

| 要求 | 结果 | 证据 |
| --- | --- | --- |
| 数量默认来自 Registry 的 case | 已实现；显式 --cases 才覆盖 | CLI 参数测试及 KUMA suite 1/2/10 数量测试 |
| 10 代表不同题目，不是重复跑一题 | 按输入内容去重，忽略 ID、空白差异 | 内容去重、批次重复拒绝测试；两份真实不同内容的 Case |
| 先向 SDK 请求 count=N | SDK 请求已参数化 | count=1/2/10 单次 POST 回归；真实 count=2 请求 |
| 批量仍被拒时临时 loop N 次 | 仅明确 case_batch_unsupported 时循环 | 实际网络顺序 2→1→1；十份 loop 测试 |
| 先收齐 N 份，再执行 | 准备容器完整返回并通过集合校验后才启动执行容器 | 正常/不足/超量/重复/中途失败回归；真实 CLI |
| Case 不足不凑数 | 失败保留部分集合，不执行 Agent | 生成失败留存测试 |
| 一个 Case 一个 Docker | 独立执行容器；另有一个不加载 Agent 的准备容器 | process.json、session.json |
| Case 内多轮，保持上下文 | 同进程、同 adapter、稳定 thread_id；自动携带完整原生消息 | 2/4 轮实测，离线原生 ReAct Docker 测试 |
| Case 之间不共享会话 | 新容器、新会话、第一轮历史为空 | 会话隔离测试与真实请求审计 |
| 保留工具调用与结果 | 完整 native messages 回传，不只拼最后回答 | 真实 Tavily 工具消息与后续输入比对 |
| 复杂调用 Trace 可追踪 | 02 的图节点、LLM、工具 OTel 父子关系和 Case/input 标识正确 | 真实 Trace 审计；不把包装层 span 数当成 HTTP 调用次数 |
| 不改原版 Agent 源码 | 上游快照与固定提交比较无差异 | git diff 对 9bbd82d84905acc37f527b1f372dae841016f3b4 |
| 不需要数据库或跨 Case 记忆 | 会话仅存在于 Case 生命周期 | AgentSession / Conversation |
| 不按 Agent 名称硬编码 | 共用生命周期与 Conversation；通过输入契约选择模式及字段 | 02 的 input-contract.json；公共 runtime 无 ReAct ID 分支 |
| 预生成官方 Case 可以执行 | 新增 SDK 导入入口，保持原始 batch/signature 信息 | SDK 导入回归、真实执行阶段生成 POST=0 |
| 保存后复用，避免重抽 | case_collection SDK 选项，原文件不修改 | 导入测试与真实保存后执行 |
| 非法集合不能进入执行 | 检查数量、索引、ID、题面及重复内容；拒绝结果落盘 | 负数/布尔索引、缺少 prompt、数量错配测试 |

已知 count=1 拒绝文本仅用于 SDK 协议兼容识别，转成稳定错误码；它不是 Agent
特判，也不是将用户的 Case 数量硬编码成 1。普通错误不触发循环降级。

## 尚未达到的验收，不能算已完成

- **十份真实收费 Case 的完整实跑尚未做。** 十份数量贯通和 loop 已有离线回归；
  真实验收按此前要求使用两份 Case，不据此宣称十份官方生成必然全部成功。
- **评分服务并非稳定完成。** 先前两份 Case 均完成 Agent 执行，但仅一份取得
  Judge 结果，另一份返回后端 model_invalid_result。返回 issue 也不等于 Agent 质量通过。
- **题目与 Agent 能力的匹配仍有问题。** 搜索型 Agent 收到过依赖构建、合同等
  流程题。ABB 不改写 SDK 题目或补造工具权限，后端题目质量不由这次 loop 修复。
- **并未证明所有 wangyi Agent 都能只配配置接入。** 通用会话机制已具备，真实
  验证的是 02；其他 Agent 仍需按原生接口、工具和生命周期逐个判断。
- 原生 interrupt/resume、跨容器崩溃恢复不在这次 Case 内多轮实现范围。

## 架构与失败边界

SDK 负责生成、原始来源校验、独立 Run 与评分；ABB 的 KUMA 边界负责准备 Case
集合和临时兼容循环；Docker runtime 负责隔离；Conversation 负责 Case 内消息。
未修改后端，未复制 wangyi 的策略校验垫片或删除 SDK 账本的重试方式。

本次循环只负责兼容数量限制，没有增加无限重试。收齐后某个 Case 执行/评分服务
失败，现有 suite 会停止该 Agent 的后续 Case，报告真实完成数，已生成集合仍保留。

具体网络证据、wangyi 生成方式与此前实测见 [BATCH-VALIDATION.md](./BATCH-VALIDATION.md)。

## 最后一次无人接续 CLI 验收

命令：`evaluate 02 --cases 2 --max-steps 2 --output results/react-loop-final`。
准备阶段成功，真实请求数量为 2→1→1，两份不同 Case 已自动收齐并通过校验，
无需手动导入或修改产物。第一份自动启动并完成两轮，执行阶段没有生成请求。
随后 Judge 返回 `model_invalid_result`，suite 按现有策略停止，第二份未执行。
因此此次结论为：**生成 2/2，Agent 执行 1/2，完整评分 0/2**，CLI 如实退出 1。
这不是 loop 出题失败，也不能当成整批评测成功。

证据：`results/react-loop-final/audit.json`；准备目录
`results/react-loop-final/7fed9e239f4e4d9293f84a9f75797344`；执行目录
`results/react-loop-final/6a6a262f20094da3b4b7facc2dc06b7b`。
原始集合保留，可用 case_collection 选项重用；未再次收费重抽。

此前保存后执行的两份 Case 均完成了各两轮，完整评分 1/2，见 BATCH-VALIDATION.md。
本次最终 ABB 回归：334 passed、11 skipped；SDK 最近一次 CI-style unittest：
551 项（1 skipped，其余通过），SDK 代码本轮未再修改。
