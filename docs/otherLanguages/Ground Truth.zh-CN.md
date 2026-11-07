# Ground truth 发现评判

[English](../Ground%20Truth.md)

GT 保存完整的 ABB Case 结果目录，每个缺陷一个目录；最外层的 `README.md`
说明各个 Case 的问题、证据和补救结果。直接保留原生
`cases/<agent-key>/<case-index>/` 的内容，不把 trace 展开塞进一个大 JSON。

```text
ground_truth/
  README.md
  issue-7303-artifact-path/
    gt.json
    case.json
    publication.json
    attempts/<attempt-id>/...
  issue-7302-sql-columns/...
  issue-7235-podcast-exit/...
```

Case 中原有的对话、工具输入输出、生成文件、错误、日志及其他流程文件都按原
目录结构保留。每个目录只新增小型 `gt.json`，schema 为
`abb.agent.ground_truth.case.v1`，包含 `agent_id`、`id`、`summary`、
`explanation` 和 `reference_attempts`。最后一项指定该 Case 的 `attempts/`
下哪些真实执行用于参考。完整字段示例见英文文档。

ABB 第一阶段仅读问题说明，总结匹配后才打开本地参考 attempt 读取 trace；
不依赖原结果目录的位置。组件探针可放在独立 `evidence/` 内，必须明确区分
组件验证和 Agent 执行。单独的对照 Case 不另算一个缺陷 GT。

不使用压缩包，不校验文件哈希，不要求两次 observation，不以完整源码
指纹相同作为评判前提。保留基本格式、安全路径和文件读取大小检查；
版本信息只用于说明来源。GT 不进入 agent 运行环境。

流程：

1. 使用已有 Judge 报告中的每条问题总结，与 GT 总结及讲解比较。
   第一阶段模型请求不包含 trace。
2. 只有总结匹配才核对双方 trace，必须引用实际事件。读取工具参数、
   返回值、错误及 artifact 记录。缺证据或超出上下文限制时记待定。
3. 同一缺陷得到双方 trace 支持记 1，明确不同记 0，证据不足记待定。
   agent 最后失败或补救成功不自动决定是否命中。
4. 同一个 GT 多次命中只计一次；任一 1 则为 1，否则有待定则保持待定。
   展示命中／未命中／待定数量，全部确定后才给最终命中率。
   缺失 Judge 报告不能当作没有发现问题。

`run` 收尾自动执行。仅评判已有结果使用：

```bash
python -m agentbench gt --suite <已有 Suite 目录>
```

此命令不生成 case、不启动 agent、不向 KUMA 提交。它只调用 ABB 匹配模型，
可通过 `ABB_GT_BASE_URL`、`ABB_GT_MODEL`、`ABB_GT_API_KEY` 配置。

请求发送前先记录。成功、失败和中断的相同请求均不自动重发。未变化的结果
直接复用；使用文件修改时间、大小和协议配置识别缓存过期，不计算文件哈希。
Suite 页面与 Benchmark 总览使用同一套结果。原始运行与 Judge 报告保持不变。

旧 manifest、匹配规则、ZIP 及展开 trace 的 ground_truth.json 需显式迁移为完整 Case 目录；
旧评判记录保留历史，不参与新协议计分。
