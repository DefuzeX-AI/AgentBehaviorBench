# ABB CLI 文档

[English](../cli.md) | 中文 | [Français](cli.fr.md) | [日本語](cli.ja.md) | [한국어](cli.ko.md)

[返回 README](README.zh-CN.md) · [如何启动 ABB](Guide.zh-CN.md) · [Agent 注册表说明](Registry.zh-CN.md) · [Agent 接入指南](How%20To%20Add%20Agent.zh-CN.md)

本文说明各命令的作用、全部公开参数、默认行为及示例。执行前请先安装 ABB，并完成目标 Agent 的配置。

将 AGENT_ID、SUITE_ID、CASE_ID、RUN_ID、源码路径及文件名替换为真实值。Agent 菜单序号以当前列表为准，Case 序号从 1 开始。OPTIONS 表示该命令表格中列出的选项。所有命令均支持 -h/--help；不带参数的 agentbench 默认执行 run。

```bash
agentbench --help
agentbench evaluate --help
agentbench agent add --help
```

agent 是命令组，必须选择子命令 add；sdk 必须选择 list 或 show。运行 agentbench agent --help 或 agentbench sdk --help 查看命令组帮助；组层级在选择子命令前仅接受 -h/--help。

## 选择命令

| 命令 | 作用与默认行为 |
| --- | --- |
| `agentbench run` | 在一个 Suite 中执行注册表内所有已启用且 status 为 ready 的 Agents，使用各自的 case 数量和 step 预算，执行前展示并确认选择。 |
| `agentbench evaluate` | 通过所选 SDK 为一个已启用 Agent 生成独立 Cases，执行 Agent、收集证据并获得 Judge 结果；不会像 certify 一样修改注册表状态。 |
| `agentbench agent add` | 导入 GitHub 仓库或本地目录。不带 -b/-c 时仅导入并列出源码；-b 生成接入配置，-c 执行认证，两者可组合使用。 |
| `agentbench certify` | 执行一个已启用 adapting Agent 在注册表中配置的 Case 数，所有请求的 Cases 无调用错误完成后晋升为 ready。Judge 发现问题本身不会阻止晋升；已 ready 的 Agent 不重复执行。 |
| `agentbench observe` | 执行一次原生输入，保存输出和轨迹，不进行 SDK 用例生成或 Judge。当前要求 Docker 的 oneshot 执行方式；--list 与 --show 用于只读查看。 |
| `agentbench view` | 通过本地网页查看已保存结果，需先构建网页资源。打开输出的完整 View 地址并保持命令运行，Ctrl+C 关闭查看器。 |
| `agentbench sdk list` | 列出 SDK 目录中发现的插件名称；这只检查发现结果，不代表所有运行依赖均已安装。 |
| `agentbench sdk show` | 加载一个 SDK 插件，显示来源、执行模式及是否允许默认选择。 |
| `agentbench resume` | 使用已保存 Cases、配置及当前凭据，继续 Suite 中符合恢复条件的未完成工作，不生成新 Cases，也不主动复跑已完成的 Cases。 |
| `agentbench retry` | 在原 Suite 中恢复一个未完成 Case，沿用原始输入。根据已保存状态恢复请求或从首轮输入重新执行，仍需满足回放条件。 |
| `agentbench reuse` | 将已保存 Case 输入用于新的 Agent 执行、证据收集及 Judge，结果保存到关联的复跑 Suite；保留原结果，不生成新输入。复跑已完成 Case 使用此命令。 |
| `agentbench clean` | 将项目 results 目录中未被引用的顶层历史归档到 cache/history-trash，保留已保存 Suites 及其引用的产物。先预览，实际清理前停止运行与查看器。 |

## `run`

在一个 Suite 中执行注册表内所有已启用且 status 为 ready 的 Agents，使用各自的 case 数量和 step 预算，执行前展示并确认选择。

```text
agentbench run [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `--sdk NAME` | 按 sdk list 中的目录名称选择 SDK；内置默认选 kuma，local 需显式指定。若多个插件均允许默认选择，必须指定名称。 | `--sdk kuma` |
| `--sdk-options PATH` | 读取 JSON 对象文件，传递所选 SDK 支持的选项；默认不传显式选项，由 SDK 提供默认值。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全可恢复的 Case 失败最多自动追加的尝试次数；非负整数，默认 2，0 表示禁用自动重试。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 首次重试的等待秒数；有限非负数，默认 5；后续等待按重试策略增长。 | `--retry-delay 5` |
| `-y, --yes` | 跳过执行确认提示；默认询问是否执行。 | `--yes` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--results-dir DIR` | 指定 ABB 结果根目录，不存在时创建；在仓库根目录运行时默认为 results/。事件保存在 DIR/suites/SUITE_ID/events.json，与旧结果位置参数互斥。 | `--results-dir results/my-run` |
| `--output PATH` | 旧 ABB 结果位置参数；文件路径仅选择父目录，不创建该文件，建议用 --results-dir。在仓库根目录运行时，默认结果根目录为 results/。 | `--output results/legacy.json` |
| `--no-view` | 保存结果但不启动网页；默认启动或复用查看器，需要已构建的网页资源。 | `--no-view` |
| `--model MODEL` | 覆盖 ABB 转发目标的模型；默认使用所选服务的配置。原生 ACP 模型按对应 Agent 配置选择。 | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | 旧流式内存暂存阈值，单位字节；默认 262144（256 KiB），不会截断保存的内容。 | `--llm-trace-max-bytes 262144` |

run 没有 --registry、--cases 或 --max-steps 参数。各 Agent 默认预算在注册表中修改；SDK JSON 的 max_steps 可覆盖轮数预算。

### 示例

```bash
agentbench run --sdk kuma
agentbench run --sdk local --yes --no-view --results-dir results/smoke
```

## `evaluate`

通过所选 SDK 为一个已启用 Agent 生成独立 Cases，执行 Agent、收集证据并获得 Judge 结果；不会像 certify 一样修改注册表状态。

```text
agentbench evaluate [AGENT] [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `-y, --yes` | 跳过执行确认提示；默认询问是否执行。 | `--yes` |
| `AGENT` | 可选的已启用 Agent ID 或菜单序号；省略时交互选择，使用 --yes 时必须指定。不要求 status 为 ready。 | `react-agent` |
| `--registry PATH` | 指定 Agent 注册表；默认使用项目的 resources/registry.toml。 | `--registry resources/registry.toml` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--model MODEL` | 覆盖 ABB 转发目标的模型；默认使用所选服务的配置。原生 ACP 模型按对应 Agent 配置选择。 | `--model openai/gpt-4.1-mini` |
| `--sdk NAME` | 按 sdk list 中的目录名称选择 SDK；内置默认选 kuma，local 需显式指定。若多个插件均允许默认选择，必须指定名称。 | `--sdk kuma` |
| `--sdk-options PATH` | 读取 JSON 对象文件，传递所选 SDK 支持的选项；默认不传显式选项，由 SDK 提供默认值。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全可恢复的 Case 失败最多自动追加的尝试次数；非负整数，默认 2，0 表示禁用自动重试。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 首次重试的等待秒数；有限非负数，默认 5；后续等待按重试策略增长。 | `--retry-delay 5` |
| `--no-view` | 保存结果但不启动网页；默认启动或复用查看器，需要已构建的网页资源。 | `--no-view` |
| `--llm-trace-max-bytes BYTES` | 旧流式内存暂存阈值，单位字节；默认 262144（256 KiB），不会截断保存的内容。 | `--llm-trace-max-bytes 262144` |
| `--results-dir DIR` | 指定 ABB 结果根目录，不存在时创建；在仓库根目录运行时默认为 results/。事件保存在 DIR/suites/SUITE_ID/events.json，与旧结果位置参数互斥。 | `--results-dir results/my-run` |
| `--result-output PATH` | 旧 ABB 结果位置参数；文件路径仅选择父目录，不创建该文件。建议用 --results-dir，两者互斥；默认项目 results/。 | `--result-output results/legacy.json` |
| `--output DIR` | SDK 产物目录，与 ABB Suite 结果目录独立；覆盖 SDK JSON 的 output。KUMA/local 默认 results/observe。 | `--output results/sdk-artifacts` |
| `--timeout SECONDS` | SDK 执行超时秒数，必须为有限正数；覆盖 SDK JSON 的 timeout。KUMA/local 默认 2400，其他 SDK 自行定义。 | `--timeout 2400` |
| `--cases N` | 独立 Case 数，必须为正整数；默认取该 Agent 注册表中的 case，本次覆盖不修改注册表。 | `--cases 1` |
| `--max-steps N` | SDK 每个 Case 的对话轮数上限，必须为正整数；覆盖注册表 step 和 SDK JSON 的 max_steps，否则沿用其默认值。部分 Agent 只支持单轮。 | `--max-steps 3` |

### 示例

```bash
agentbench evaluate react-agent --sdk kuma --cases 1
agentbench evaluate react-agent --sdk local --cases 1 --yes --no-view --results-dir results/smoke
agentbench evaluate react-agent --sdk kuma --cases 2 --max-steps 3 --output results/sdk-artifacts --results-dir results/my-run --no-view
```

## `agent add`

导入 GitHub 仓库或本地目录。不带 -b/-c 时仅导入并列出源码；-b 生成接入配置，-c 执行认证，两者可组合使用。

```text
agentbench agent add SOURCE [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `SOURCE` | 必填的 HTTPS GitHub 仓库 URL 或本地绝对目录，不接受分支/文件页面 URL。普通导入创建单元，-b/-c 可复用匹配的已导入源码。 | `https://github.com/langchain-ai/react-agent` |
| `--agents-dir DIR` | 带编号 Agent 单元的父目录；默认是项目默认注册表旁的 resources/agents。生成的单元必须位于 --registry 对应根目录内。 | `--agents-dir resources/agents` |
| `-b, --build` | 生成、校验并保存接入配置，完成后登记为 adapting，可复用已完成且有效的文件。支持 LangGraph 和 ACP；不构建 Docker。默认关闭。 | `-b` |
| `-c, --certify` | 校验已生成或人工准备的接入文件，注册后执行认证；不会隐式启用 -b。默认关闭。 | `-c` |
| `--registry PATH` | 指定 Agent 注册表；默认使用项目的 resources/registry.toml。 | `--registry resources/registry.toml` |
| `--build-settings PATH` | 带 [build] 表的 TOML 文件，覆盖生成预算和模型等；默认使用内置配置，配合 -b 使用。 | `--build-settings build-settings.toml` |
| `--build-model MODEL` | -b 配置生成使用的 OpenRouter 模型。优先级：本参数、[build].model、OPENROUTER_BUILD_MODEL、OPENROUTER_MODEL；需支持结构化输出。 | `--build-model openai/gpt-4.1-mini` |
| `--answers PATH` | 回答上一轮生成规划问题的 UTF-8 文本文件；携带该文件重复 -b 命令。默认不提供回答文件。 | `--answers answers.txt` |
| `--with-observe` | -b 时生成 observe 交互输入字段；默认关闭，不带 -b 时不接受。 | `--with-observe` |
| `--agent-timeout SECONDS` | -b 时设置生成的 Agent 运行超时，单位秒，必须为有限正数；默认 300，不是配置生成请求的超时。 | `--agent-timeout 600` |
| `--adapter-context PATH` | -b 时读取明确的部署上下文 JSON 对象，文件不超过 64 KiB；默认不覆盖上下文，内容须符合该 Agent 的接入方式。 | `--adapter-context adapter-context.json` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--model MODEL` | -c 认证时的转发目标模型，与 --build-model 独立；默认取服务配置，原生 ACP 模型选择按 Agent 配置。 | `--model openai/gpt-4.1-mini` |
| `--output PATH` | -c 的认证结果位置；对于托管 Suite，文件路径只选择父目录，不创建该文件，默认项目 results/。本命令没有 --results-dir 参数。 | `--output results/add-certification.json` |
| `--no-view` | -c 时保存认证结果但不启动网页；不影响源码导入或配置生成，默认认证启用查看器。 | `--no-view` |
| `-y, --yes` | 跳过 -c 认证的执行确认；默认询问，不会自动回答生成规划的问题。 | `--yes` |
| `--sdk NAME` | 按 sdk list 中的目录名称选择 SDK；内置默认选 kuma，local 需显式指定。若多个插件均允许默认选择，必须指定名称。 | `--sdk kuma` |
| `--sdk-options PATH` | 读取 JSON 对象文件，仅向 -c 认证传递 SDK 选项，不用于 -b 配置生成；默认使用 SDK 默认值。 | `--sdk-options sdk-options.json` |

本地路径必须为绝对路径；Windows 可写 "C:\work\local-agent"。不接受 -d。当前配置生成使用 OpenRouter，并要求 SDK 具备接入校验接口；内置 local 不提供该接口。

### 示例

```bash
agentbench agent add https://github.com/langchain-ai/react-agent
agentbench agent add /absolute/path/to/local-agent -b --sdk kuma --build-model openai/gpt-4.1-mini
agentbench agent add /absolute/path/to/local-agent -b -c --sdk kuma --no-view
```

## `certify`

执行一个已启用 adapting Agent 在注册表中配置的 Case 数，所有请求的 Cases 无调用错误完成后晋升为 ready。Judge 发现问题本身不会阻止晋升；已 ready 的 Agent 不重复执行。

```text
agentbench certify AGENT_ID [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `-y, --yes` | 跳过执行确认提示；默认询问是否执行。 | `--yes` |
| `--registry PATH` | 指定 Agent 注册表；默认使用项目的 resources/registry.toml。 | `--registry resources/registry.toml` |
| `--sdk NAME` | 按 sdk list 中的目录名称选择 SDK；内置默认选 kuma，local 需显式指定。若多个插件均允许默认选择，必须指定名称。 | `--sdk kuma` |
| `--sdk-options PATH` | 读取 JSON 对象文件，传递所选 SDK 支持的选项；默认不传显式选项，由 SDK 提供默认值。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全可恢复的 Case 失败最多自动追加的尝试次数；非负整数，默认 2，0 表示禁用自动重试。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 首次重试的等待秒数；有限非负数，默认 5；后续等待按重试策略增长。 | `--retry-delay 5` |
| `--no-view` | 保存结果但不启动网页；默认启动或复用查看器，需要已构建的网页资源。 | `--no-view` |
| `AGENT_ID` | 必填的已启用注册 Agent 精确 ID；认证 adapting Agent，ready Agent 直接返回，不再次执行。 | `folder-mover-agent` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--results-dir DIR` | 指定 ABB 结果根目录，不存在时创建；在仓库根目录运行时默认为 results/。事件保存在 DIR/suites/SUITE_ID/events.json，与旧结果位置参数互斥。 | `--results-dir results/my-run` |
| `--output PATH` | 旧 ABB 结果位置参数；文件路径仅选择父目录，不创建该文件，建议用 --results-dir。在仓库根目录运行时，默认结果根目录为 results/。 | `--output results/legacy.json` |
| `--model MODEL` | 覆盖 ABB 转发目标的模型；默认使用所选服务的配置。原生 ACP 模型按对应 Agent 配置选择。 | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | 旧流式内存暂存阈值，单位字节；默认 262144（256 KiB），不会截断保存的内容。 | `--llm-trace-max-bytes 262144` |

### 示例

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
agentbench certify AGENT_ID --sdk local --yes --no-view --results-dir results/certification
```

## `observe`

执行一次原生输入，保存输出和轨迹，不进行 SDK 用例生成或 Judge。当前要求 Docker 的 oneshot 执行方式；--list 与 --show 用于只读查看。

```text
agentbench observe [AGENT] [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `AGENT` | 可选的已启用 Agent ID 或菜单序号，省略时交互选择；与 --agent 互斥。 | `react-agent` |
| `--agent AGENT` | 位置参数的替代写法，接受 Agent ID 或菜单序号，不能同时使用两种写法。 | `--agent react-agent` |
| `--registry PATH` | 指定 Agent 注册表；默认使用项目的 resources/registry.toml。 | `--registry resources/registry.toml` |
| `--list` | 列出已启用 Agents 后退出，不执行 Agent；默认关闭。 | `--list` |
| `--input PATH` | 从 UTF-8 JSON 文件读取一次原生输入；文本输入需写成带引号的 JSON 字符串。默认按 observe 字段或原始 JSON 交互输入。 | `--input native-input.json` |
| `--output DIR` | Observe 产物根目录，执行时创建 run ID 子目录；默认 results/observe。 | `--output results/observe` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--model MODEL` | 覆盖 ABB 转发目标的模型；默认使用所选服务的配置。原生 ACP 模型按对应 Agent 配置选择。 | `--model openai/gpt-4.1-mini` |
| `--timeout SECONDS` | 覆盖 Agent 执行超时秒数，必须为有限正数；默认使用该 Agent 的运行配置。 | `--timeout 300` |
| `--show DIR` | 离线查看已保存的 observe 执行目录并退出，不执行 Agent，也不使用其他执行参数。 | `--show results/observe/RUN_ID` |

### 示例

```bash
agentbench observe --list
agentbench observe react-agent --input native-input.json --output results/observe --timeout 300
agentbench observe --show results/observe/RUN_ID
```

## `view`

通过本地网页查看已保存结果，需先构建网页资源。打开输出的完整 View 地址并保持命令运行，Ctrl+C 关闭查看器。

```text
agentbench view RESULT_LOG [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `RESULT_LOG` | 必填的已存在 JSON 结果文件，通常为 Result saved 输出的 events.json；传文件而非目录。 | `results/suites/SUITE_ID/events.json` |
| `--host ADDRESS` | 网页监听地址；默认 127.0.0.1。 | `--host 127.0.0.1` |
| `--port N` | 监听端口，范围 0–65535，默认 8765；0 表示自动分配。默认端口被占用时可选用其他空闲端口。 | `--port 0` |

### 示例

```bash
agentbench view results/suites/SUITE_ID/events.json
agentbench view results/suites/SUITE_ID/events.json --host 127.0.0.1 --port 0
```

## `sdk list`

列出 SDK 目录中发现的插件名称；这只检查发现结果，不代表所有运行依赖均已安装。

```text
agentbench sdk list [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |

### 示例

```bash
agentbench sdk list
```

## `sdk show`

加载一个 SDK 插件，显示来源、执行模式及是否允许默认选择。

```text
agentbench sdk show NAME [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `NAME` | 必填的 SDK 目录名称，不区分大小写，使用 sdk list 中的名称。 | `kuma` |

### 示例

```bash
agentbench sdk show kuma
agentbench sdk show local
```

## `resume`

使用已保存 Cases、配置及当前凭据，继续 Suite 中符合恢复条件的未完成工作，不生成新 Cases，也不主动复跑已完成的 Cases。

```text
agentbench resume SUITE [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `SUITE` | 必填的已保存 Suite ID、目录或 events.json 路径；ID 在 --suite-root 下解析。 | `results/suites/SUITE_ID` |
| `--suite-root DIR` | 包含 Suite ID 目录的父目录；默认当前工作目录下的 results/suites。 | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |

### 示例

```bash
agentbench resume results/suites/SUITE_ID
agentbench resume SUITE_ID --suite-root results/my-run/suites --env-file .env.testing
```

## `retry`

在原 Suite 中恢复一个未完成 Case，沿用原始输入。根据已保存状态恢复请求或从首轮输入重新执行，仍需满足回放条件。

```text
agentbench retry SUITE --agent ID --case N [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `SUITE` | 必填的已保存 Suite ID、目录或 events.json 路径；ID 在 --suite-root 下解析。 | `results/suites/SUITE_ID` |
| `--suite-root DIR` | 包含 Suite ID 目录的父目录；默认当前工作目录下的 results/suites。 | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--agent ID` | 必填的原 Suite 中的精确 Agent ID，不是菜单序号。 | `--agent react-agent` |
| `--case N` | 必填的 Case 序号，从 1 开始，必须为正整数，选择 --agent 的该 Case。 | `--case 1` |

### 示例

```bash
agentbench retry results/suites/SUITE_ID --agent react-agent --case 1
```

## `reuse`

将已保存 Case 输入用于新的 Agent 执行、证据收集及 Judge，结果保存到关联的复跑 Suite；保留原结果，不生成新输入。复跑已完成 Case 使用此命令。

```text
agentbench reuse SOURCE [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `SOURCE` | 必填的已保存 Suite ID/路径、Case ID、artifact run ID、case.json 或执行产物路径。Suite 默认选全部 Cases；--agent 与 --case 可定位一个，歧义 ID 需指定来源。 | `CASE_ID` |
| `--suite-root DIR` | 限制在该目录中查找已保存 Suite；默认查找项目 results 及已登记的外部 Suites。 | `--suite-root results/my-run/suites` |
| `--agent ID` | 来源为 Suite 时选择精确 Agent ID，必须与 --case 一起使用；两者均省略时复跑全部 Cases。 | `--agent react-agent` |
| `--case N` | Suite 中从 1 开始的正整数 Case 序号，必须与 --agent 一起使用，不与直接 Case ID 混用。 | `--case 2` |
| `--output-root DIR` | 复跑 Suite 的父目录；新 Suite 保存在 DIR/SUITE_ID，默认使用来源 Suite 的父目录。仅加入直接位于该目录内的兼容活跃复跑 Suite。 | `--output-root results/reruns` |
| `--env-file PATH` | 指定环境文件；默认读取项目 .env，Shell 已导出的变量优先。 | `--env-file .env.testing` |
| `--model MODEL` | 新评测的转发目标模型；默认使用保存的模型设置，原生 ACP 模型选择仍按 Agent 配置。 | `--model openai/gpt-4.1-mini` |
| `--max-steps N` | 新评测的 SDK 对话轮数预算，必须为正整数；默认保存的运行设置，不会给已保存 Case 生成额外输入。 | `--max-steps 3` |

兼容的请求可能加入正在运行的复跑 Suite，每次主动请求都增加一次新执行。本命令没有 --no-view、--yes、--sdk 或 --cases 参数，会输出结果/查看器链接。

### 示例

```bash
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent react-agent --case 2
agentbench reuse results/suites/SUITE_ID --output-root results/reruns --max-steps 3
```

## `clean`

将项目 results 目录中未被引用的顶层历史归档到 cache/history-trash，保留已保存 Suites 及其引用的产物。先预览，实际清理前停止运行与查看器。

```text
agentbench clean [OPTIONS]
```

| 参数 | 作用与默认行为 | 示例 |
| --- | --- | --- |
| `-h, --help` | 显示当前命令的帮助并退出。 | `--help` |
| `--dry-run` | 预览待归档内容，不移动文件；默认关闭。 | `--dry-run` |
| `-y, --yes` | 跳过归档确认，默认询问；实际清理前停止运行与查看器。 | `--yes` |

### 示例

```bash
agentbench clean --dry-run
agentbench clean
```

## 示例中使用的文件

使用对应参数前先创建这些文件。JSON 文件必须是有效 JSON，sdk-options.json 必须为对象。以下 SDK 选项适用于 kuma/local，其他插件可能支持不同字段。

`sdk-options.json`:

```json
{
  "timeout": 2400,
  "max_steps": 3
}
```

`build-settings.toml`:

```toml
[build]
model = "openai/gpt-4.1-mini"
timeout_seconds = 120
```

`native-input.json`:

```json
"Describe your capabilities and limitations."
```

native-input.json 必须符合 Agent 的原生输入格式。answers.txt 写入规划问题的实际回答。adapter-context.json 是配合 -b 使用的部署上下文对象，字段取决于 Agent，没有通用的可直接复制对象。
