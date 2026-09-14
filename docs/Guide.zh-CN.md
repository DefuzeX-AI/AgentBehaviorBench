# 中文操作与排错指南

ABB 负责选 Agent、Docker、并发、证据收集和本地结果。Kuma 负责
Case → Input → Submission → Report 协议，官方 Case/Judge 由 DefuzeX 服务提供。
Judge 的 issue 表示发现行为问题，不等于程序运行失败。

先按 [README](../README.md) 安装。在仓库根目录执行免费离线示例：

```bash
python -m examples.offline_demo
```

它使用本地 echo Agent 和确定性 Judge，不需要 Docker、账号、网络或密钥，
不能代替官方服务验收。实际运行前启动 Docker，填写本地 `.env`。模型名称必须
显式配置；模板的名称只是示例。KUMA_API_KEY 非空时优先于 DEFUZEX_API_KEY；
shell 已导出的变量优先于 dotenv。不要上传密钥或原始含密日志。

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1 --yes --no-view
agentbench certify react-agent --cases 1 --yes --no-view
agentbench run --yes --no-view
```

evaluate 可以测试启用的 adapting Agent。certify 实际执行成功后才会写 ready，
正常 Judge issue 不阻止认证。run 只选 enabled 且 ready 的 Agent。
`--yes` 跳过确认；`--no-view` 只关闭 viewer。`--cases` 是独立 Case 数量，
`--max-steps` 是每 Case 的对话轮数上限，实际轮数可能更少；它不限制内部工具调用数。
`ABB_MAX_PARALLEL_CASES=4` 表示共享四个 Case worker，同一 Case 内的 Input 顺序执行。

终端会打印真实保存路径。`agentbench view 路径` 可以重开结果。单个 Case 失败时，
其他 Case 已完成结果仍会保存。Judge 收到后宿主拒绝的情况会保留报告引用并明确
标记 host_accepted=false。先看 Case 的错误、SDK 错误码与请求 ID，再看相关网络错误；
不要因为响应丢失就直接重复创建付费请求。

新 Agent 接入顺序：下载并记录官方 commit → 保留许可证 → 写 binding / Docker /
agent.toml / Kuma profile → 登记 adapting → observe → evaluate → 实际 certify。
工具必须真实调用；声明必需路由与密钥变量名；记录每个接入问题及修复。
之后逐步测 1/2/3/5 轮，检查同 Case 历史延续和不同 Case 互相隔离。

完整接口与深入设计目前以英文为准：[CLI](CLI.md)、[接入说明](How%20To%20Add%20Agent.md)、
[故障表](Troubleshooting.md)、[SDK 适配](SDK-Directory-Adapters.md)。其余语言 README 是
入门翻译，未宣称覆盖全部开发文档。官方 SDK 的
[中文指南](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/sdk-guide.zh-CN.md)
和[中文诊断](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/public-error-diagnostics.zh-CN.md)
用于核对真实协议。
