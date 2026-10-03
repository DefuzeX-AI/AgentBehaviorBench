# 如何阅读 `registry.toml`

[English](../Registry.md) | 中文 | [Français](Registry.fr.md) | [日本語](Registry.ja.md) | [한국어](Registry.ko.md)

[返回 README](README.zh-CN.md) · [如何启动 ABB](Guide.zh-CN.md)

[Agent 注册表](../../resources/registry.toml) 记录 ABB 可使用的目标 Agents、本地接入目录
及默认评测预算。`agentbench run` 选择同时满足 `enabled = true` 和 `status = "ready"`
的条目。

## 阅读一个条目

文件开头声明格式版本；每个 `[[agents]]` 块注册一个 Agent：

```toml
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "folder-mover-agent"
path = "resources/agents/01-folder-mover-agent"
enabled = false
status = "ready"
framework = "langgraph"
source = "C:\\Song_startup\\benchmark\\04-folder-mover-agent\\folder-mover-agent"
case = 1
step = 3
```

这个例子注册了一个 LangGraph Agent，默认执行一个独立 Case，每个 Case 最多包含三轮
对话。它已标记为 `ready`，但 `enabled = false`，因此不会被 `run` 选中。`source` 中的
本地路径是某台机器上的原始导入位置示例，使用者无需创建相同的目录。

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 整个注册表的格式标识。保持为 `"defuzex-bench.registry.v1"`，在所有 Agent 块之前写一次。 |
| `[[agents]]` | TOML 的表数组语法，每个块代表一个独立的 Agent 注册条目。 |
| `agent_id` | Agent 的唯一标识，用于 CLI 命令。必须与该 Agent 的 `agent.toml` 中的 `agent_id` 一致。 |
| `path` | 本地接入目录。在标准注册表位置下，相对于仓库根目录解析。指向包含 `agent.toml` 和 `requirement.md` 的外层目录，而非内部的 `agent/` 源码目录；必须位于仓库内。 |
| `enabled` | 是否允许选择该 Agent。`false` 会将它排除在 `run` 和单 Agent 的 `evaluate` 选择之外。使用 TOML 布尔值，省略时默认为 `true`。 |
| `status` | 接入阶段标记。`adapting` 表示接入待认证；`ready` 表示启用后可参与默认 `run`。省略时为 `unknown`，不会被 `run` 选中。 |
| `framework` | 框架标记，例如 `langgraph` 或 `acp`，应与 Agent 的配置及实际接入方式一致。运行时 Adapter 和启动配置由 `agent.toml` 定义。 |
| `source` | 原始源码来源，例如仓库 URL 或本地导入目录。用于记录来源；修改它不会替换已导入的源码或改变启动配置。省略时为空字符串。 |
| `case` | 为该 Agent 执行的独立 Case 数量，必须是正整数；省略时默认为 `1`。 |
| `step` | SDK 对每个 Case 的对话轮数上限，填写时必须是正整数；省略时使用 SDK 的默认值。实际 Case 可以少于该轮数。 |

`agent_id`、`path` 和 `framework` 为必填的非空字符串。在 TOML 双引号字符串中，
Windows 路径的反斜杠需要写成 `\\`，如上面的示例。

## 区分 `case` 和 `step`

- `case = 1`、`step = 3`：一个独立 Case，最多包含三轮按顺序提交的输入。
- `case = 5`、`step = 3`：五个独立 Cases，每个 Case 最多包含三轮输入。
- 一轮对话向目标 Agent 提交一次输入，执行过程中可能包含多次模型调用和工具调用。
  因此，`step` 不是工具调用次数或 Agent 内部推理循环次数的上限；`case` 和 `step`
  也不设置并发数。

部分 Agent 不支持多轮输入，因此建议保留 Benchmark 为各 Agent 配置的默认 `step` 值。

所选 SDK 在用例生成和执行时使用轮数预算。显式设置的 SDK `max_steps` 选项优先于
注册表的 `step`。对于 `evaluate`，`--cases` 覆盖本次执行的 `case`，`--max-steps`
覆盖本次执行的轮数预算，均不会修改注册表：

```bash
agentbench evaluate react-agent --cases 2 --max-steps 3 --no-view
```

## 选择 Agent 与调整默认值

要让示例 Agent 参与 `run`，将其 `enabled` 改为 `true`。对于标记为 `adapting` 的新接入
Agent，请先完成[接入配置](How%20To%20Add%20Agent.zh-CN.md)，在启用状态下进行认证：

```bash
agentbench certify folder-mover-agent --no-view
```

认证通过后，ABB 将成功接入的 Agent 标记为 `ready`。该状态说明接入就绪，不保证 Judge
不会发现行为缺陷；手动修改状态不会执行认证。与 `run` 不同，`evaluate` 可以选择已启用
的 Agent，不按 `ready` 状态筛选。

```bash
agentbench observe --list
agentbench run --no-view
```

修改 `case`、`step` 会调整后续执行的默认预算，已保存的 Cases 和结果保留原有配置。
`run` 在筛选启用且 ready 的 Agents 之前，会加载并校验所有注册条目，因此已禁用的条目
若缺少接入文件，仍可能导致注册表加载失败。请保持路径有效、标识唯一，并保留必需的
接入文件。注册源码清单见[已加入的 Agents](Agents.zh-CN.md)。
