# AgentBehaviorBench（ABB）

<p align="center">
  <img
    alt="AgentBehaviorBench — 对 Agent 工作流进行行为评测"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  中文 |
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 或更高版本" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## ABB 是什么？

AgentBehaviorBench（ABB）是一个用于评估 AI Agent 行为测试能力的基准。它包含两部分数据：可直接启动的目标 Agents，以及通过人工实际测试确认的行为缺陷，作为 Ground Truth。参与评测的测试 Agent 需要生成测试用例，让目标 Agent 执行这些用例，并分析执行过程中产生的行为轨迹，以发现目标 Agent 存在的问题。

## 概览

ABB 通过不同的 Adapters 接入由不同框架实现的目标 Agents，并在统一的 Pipeline 中执行测试用例、收集行为证据。接入 ABB 的测试 Agent 需要具备生成测试用例、分析执行证据以及作出缺陷判定（Judge）的能力，并通过评测 SDK 与 ABB 对接。执行证据包括测试输入、Agent 输出与执行状态、OpenTelemetry 调用轨迹，以及启用文件采集后的文件变化记录与 Diff。测试 Agent 应基于这些证据报告发现的行为缺陷；在基准评测中，成功识别 Ground Truth 中指定的缺陷将获得相应得分。

每个参与 AgentBehaviorBench 评测的**测试 Agent** 应具备以下能力：

1. **测试用例生成（Case Generation）**：根据目标 Agent 的功能与行为约束，生成用于检验其行为的测试用例。
2. **行为轨迹分析（Trajectory Analysis）**：分析测试输入、Agent 输出、OpenTelemetry 调用轨迹及文件变化证据，识别潜在的行为异常。
3. **缺陷判定（Judging）**：基于执行证据判断目标 Agent 是否存在行为缺陷，并报告具体问题及其证据依据。

![AgentBehaviorBench 架构](../figures/abb-suite-sdk-roles.png)

Agent Registry 记录当前测试的是哪个 Agent 源码版本，以及 ABB 应当如何启动它。ABB Harness
负责调度 Cases、启动隔离容器、执行 Agent Run、路由已声明的模型和工具流量，以及采集调用链
和文件系统证据。Agent 的执行状态与 Judge 判定是两个不同的概念：容器和 Agent 可能成功执行，
但 Judge 仍然可能发现行为问题。

## 资源

- [已加入的 Agents](Agents.zh-CN.md) — 目标 Agent 清单、源码来源及固定版本。
- [如何阅读 Agent 注册表](Registry.zh-CN.md) — `registry.toml` 字段、Agent 选择与 Case 预算。
- [如何添加 Agent](How%20To%20Add%20Agent.zh-CN.md)
- [CLI 文档](cli.zh-CN.md)
- [如何启动 ABB](Guide.zh-CN.md)
- [结果说明和故障排查（英文）](../Troubleshooting.md)

## 许可证

MIT，详见 [LICENSE](../../LICENSE)。
