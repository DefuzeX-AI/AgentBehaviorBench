# DeerFlow Ground Truth

这里保存 3 个完整的 ABB Case 结果目录。目录内容直接复制自已有运行，
保留 `case.json`、`generation.json`、`publication.json` 和整个 `attempts/`。
没有重跑 Agent，也没有向 KUMA 重新提交。每个目录里的 `gt.json` 只是简短的
问题说明与参考 attempt 索引，不展开或复制 trace。

| Case 目录 | 对应问题 | 参考流程中的实际证据 | Agent 补救与任务结果 |
| --- | --- | --- | --- |
| [issue-7303-artifact-path](issue-7303-artifact-path/) | [#7303](https://github.com/bytedance/deer-flow/issues/7303)：带空格的产物路径被截断 | 创建带空格的路径 → ArtifactCapture 登记截断路径 → 读取失败 → 使用完整路径读回 CHECKPOINT-7303 | 完整路径补救成功，但后续再次尝试截断引用，最终递归超限 |
| [issue-7302-sql-columns](issue-7302-sql-columns/) | [#7302](https://github.com/bytedance/deer-flow/issues/7302)：SQL 重复列名导出 JSON 丢值 | 两列同名 id，值为 1 和 2 → JSON 仅剩 id=2；不同列名对照保留两值 | Agent 识别丢值并比较其他格式，最终递归超限 |
| [issue-7235-podcast-exit](issue-7235-podcast-exit/) | [#7235](https://github.com/bytedance/deer-flow/issues/7235)：播客生成失败仍返回退出码 0 | 生成报错、无 MP3，但进程返回 0；参数错误对照返回 2 | Agent 正确指出失败，诊断任务完成；没有恢复音频生成 |

## 怎样查看

每个 Case 的 `case.json` 保存任务输入；`attempts/<id>/run.json` 保存执行状态。
`attempts/<id>/evaluation/inputs/` 中保存原始输入、输出、OTel trace 及其 payload，
其余 `channel/`、`replay/`、`agent-output/` 等内容按原目录结构保留。
`evidence/` 保留已有的 3 次组件探针结果，不能当作 3 次 Agent 运行。

三个 Case 来自 `suite_4a9ae480fe9348eca2f14d832176637c` 的 case 0、2、3。
#7303 的无空格对照是原 Suite 中单独的 case 1，仍保留在原结果目录；
它不另算一个 GT。本目录只放三个缺陷对应的 Case。
原始结果中的历史路径只用于溯源；ABB 读取本地复制后的相对路径，不依赖旧结果目录。

## ABB 如何评判

先用已有 Judge 问题总结比较 `gt.json` 的 `summary` 和 `explanation`。
总结匹配后，才从 `reference_attempts` 指定的本地原始目录读取 trace，与本轮
trace 对照。缺陷命中计 1、明确不符计 0、证据不足待定；补救结果单独记录。
不根据执行成功/失败直接判断 GT，不使用 ZIP 或文件哈希。
