# 在新 Suite 中复用 Case

继续原配置、补齐原结果使用 `agentbench resume <suite>`。修改 Agent 源码、模型或运行参数后，需要新建 Suite，避免混合不同配置的评分：

```bash
agentbench reuse suite_original
agentbench reuse suite_original --model provider/model --max-steps 5
```

`reuse` 复用原 Suite 的全部 Agent 和 Case 位置，逐个检查并复制完整 Case 文件，保留 Case ID、内容摘要和字节摘要。它不会重新请求 CaseGen；任意 Case 缺失或损坏时会直接报错，不会偷偷补生成。

新 Suite 采用当前源码和 SDK 依赖指纹。模型、并发及 SDK 配置默认沿用原计划；`--model` 和 `--max-steps` 通过普通运行配置覆盖。已有 Case 文件及其输入顺序保持原样；`max_steps` 的实际执行效果由所选 SDK 的公开能力决定。

新计划记录 `origin_suite_id`，每个 Case 记录原 Suite/Agent/位置。旧 Attempt、SDK Run、Agent 输出和 Judge 报告不会复制或参与新评分。原 Suite 保持不变；新 Suite 执行中断后，可以对新 ID 使用 `resume`。

支持 `--suite-root` 查找原 Suite、`--output-root` 指定新 Suite 的父目录，以及 `--env-file` 使用当前凭据。默认在原 Suite 的同级目录创建新 Suite。
