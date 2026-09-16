# AgentBehaviorBench (ABB)

[English](../../README.md) · [中文安装与操作指南](Guide.zh-CN.md)

ABB 运行 Agent、隔离 Case、收集输入输出及工具/OTel 证据；KUMA SDK 调用 DefuzeX
服务生成 Case 和评判行为。评测发现 issue 与容器执行失败是不同结果。

![AgentBehaviorBench 执行架构](../figures/framework.png)

## 前置条件

- Git、Python 3.10+（含 pip/venv）。
- Docker Agent 需要已启动、当前用户可访问的 Docker：先运行 `docker info`。
- 网页构建需要 Node.js 20.x 至少 20.19 或 22.12+，以及 npm。在 web/ 执行
  `npm ci`、`npm run build`。普通网页由 Python 提供，不需要一直运行 npm。
- 无界面评测可使用 `--no-view`，不需要 Node/网页构建。
- 正式 KUMA 评测需要 KUMA key、OpenRouter key 和模型名称，以及 Agent 自己的工具
  key。离线示例和查看已保存结果不需要这些凭据。

## 从安装到首次运行

完整可复制命令、Windows/WSL 与 Docker 平台说明、凭据链接及优先级见
[中文操作指南](Guide.zh-CN.md)。先完成不需要 Docker/key 的离线示例，再配置正式服务。

- [零凭据验证与网页构建](Guide.zh-CN.md#零凭据验证与网页构建)
- [配置真实评测](Guide.zh-CN.md#配置真实评测)
- [添加 Agent](How%20To%20Add%20Agent.zh-CN.md)
- [结果与故障处理](Guide.zh-CN.md#结果与故障处理)
- [逐文件 Agent 接入指南](How%20To%20Add%20Agent.zh-CN.md)
- [网页开发指南（英文）](../../web/README.md)
- [文档 issue 核对记录（英文）](../Documentation-Issue-Audit.md)

当前 Agent、启用状态和 Case 数以 [注册表](../../resources/registry.toml) 为准。
全部 CLI 参数使用 `agentbench --help` 和 `agentbench COMMAND --help` 查看。

贡献约定见 [AGENTS.md（英文）](../../AGENTS.md)。MIT，见 [LICENSE](../../LICENSE)。
