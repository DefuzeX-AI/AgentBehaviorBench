# 添加 Agent

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | 中文 | [한국어](How%20To%20Add%20Agent.ko.md)

[如何启动 ABB](Guide.zh-CN.md) · [CLI 文档](cli.zh-CN.md) · [注册表说明](Registry.zh-CN.md)

在 ABB 仓库根目录、已激活的虚拟环境中，按环境配置、导入源码、生成接入文件、审核和测试的顺序操作。将 SOURCE、AGENT_ID、NN-name 和结果路径替换为实际值。

## 1. 配置环境

安装 Git 和 Python 3.10+，按上方启动指南安装 ABB。执行 Agent 和认证时，当前用户需要能使用 Docker。使用 KUMA 生成或校验配置时，在运行 ABB 的同一个虚拟环境中安装 KUMA：

```bash
python -m pip install -e .
python -m pip install "kuma-defuzex[otel]>=0.3.3"
git --version
agentbench --help
agentbench sdk list
docker info
```

`sdk list` 只列出插件，不验证依赖是否安装。源码导入和配置生成不需要 Docker；宿主机与容器中的 SDK 安装相互独立。

仅在 `.env` 不存在时复制 `.env.example`，然后在本地编辑。KUMA 需要 KUMA_API_KEY（或 DEFUZEX_API_KEY）；配置生成使用 OpenRouter，模型必须支持严格结构化输出：

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate generation model:
# OPENROUTER_BUILD_MODEL=
```

被测 Agent 的运行模型单独配置：LangGraph 接入可使用 OpenRouter、DeepSeek 或 GLM；原生 ACP Agent 使用自身声明的服务凭据，见启动指南。`--build-model` 选择配置生成模型，`--model` 选择认证时 ABB 转发目标的模型。Shell 导出的变量优先于 `.env`，不要把真实 key 写入源码或生成文件。

网页需要 npm，以及 Node.js 20.x 至少 20.19 或 22.12+；随后构建网页。使用 `--no-view` 的无界面评测不要求 Node 或 `web/dist`。

```bash
cd web
npm ci
npm run build
cd ..
```

## 2. 导入源码并生成配置

SOURCE 必须是 HTTPS GitHub 仓库地址本身（不能是文件或分支页面），或本地绝对目录。GitHub 导入默认分支，没有 `--revision` 参数；本地导入排除 `.git` 并记录内容摘要。先导入源码：

```bash
agentbench agent add https://github.com/owner/repository
```

`agent add` 还会在 `agent/` 同级创建 `ground_truth/.gitkeep`，复用已导入的 Agent 时也会补齐。占位文件用于让 Git 保留目录；已确认的缺陷和证据仍需按 [Ground Truth](Ground%20Truth.zh-CN.md) 手动准备。

然后用同一来源生成接入文件。不带 `-b` 或 `-c` 重复普通导入会报重复；这两个选项可复用匹配的已导入单元，不会从已变化的源码目录刷新快照。本地来源可用 `/absolute/path/to/local-agent`，PowerShell 可用 `"C:\work\local-agent"`。

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma
```

`-b` 支持 LangGraph 和 ACP，生成、校验接入文件并注册为 `adapting`，不会构建 Docker。KUMA 在规划前查询当前策略目录。内置 `local` 支持评测但没有接入校验接口，这个生成流程使用 KUMA。规划需要补充信息时，将真实部署说明写入 UTF-8 的 `answers.txt`，再加 `--answers answers.txt` 重复命令；失败后保留已完成且有效的文件，重试前查看保存的 `build-result.json`。

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma --answers answers.txt
```

## 3. 了解每个文件的用途

Agent 单元位于 `resources/agents/NN-name/`。命令在导入的源码外围生成接入文件，
不需要在运行命令前手写齐全。

```text
resources/agents/NN-name/
├── agent/                   # 导入的上游或本地源码快照
├── agent.toml               # ABB execution configuration
├── bindings/                # LangGraph binding; not required for native ACP
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 自身源码

保存导入的上游或本地源码快照。真实图、推理和工具仍在这里实现。ABB 接入文件放在目录外，
避免接入时悄悄替换原 Agent 的行为。

### `agent.toml` — ABB 如何启动和调用 Agent

声明 ID、框架、源码 revision、镜像构建/启动设置、适配器、输入输出映射、环境和
模型/工具路由。核对入口路径和必需输入。声明路由或变量不会实现工具，也不会启动服务。

### `bindings/*.py`

LangGraph 的 binding 导出同步、无参数工厂，返回真实可调用的 Agent，并处理原生输入输出和生命周期清理。ACP 接入通过 `agent.toml` 中配置的原生命令和协议运行，不要求 Python binding 工厂。两种接入都应保留 Agent 本身的行为。

具体文件布局、调用示例、config 转发、原生生命周期和验证方法，见 [LangGraph binding 编写手册](LangGraph%20Bindings.zh-CN.md)。

### `Dockerfile` — 容器内安装什么

安装 Agent 的 Python/系统依赖，复制源码、binding 和配置。检查 CPU 架构、解释器、
可写位置及 Agent 专属浏览器/Node 需求。当前 KUMA overlay 用 `python -m pip`
安装 SDK，因此该解释器需要支持 pip。

### `.dockerignore` — 哪些文件不进入构建

排除凭据、宿主机 venv、缓存和结果，同时保留镜像必需的源码与配置。
`-b` 使用 ABB 模板生成此文件。

### `requirement.md` — 评测什么

描述已部署 Agent 的用途、可观察行为、真实工具和限制。KUMA 要求 YAML front matter，
以及 Production Use Scenario、Behaviors to Test、Known Limitations or Prohibited
Behaviors 三个章节；策略组从当前 SDK 目录选取。

写当前能力，而非潜在扩展。只有搜索工具的 Agent 能解释计算，但不能执行采样器或保存
文件。明确缺少能力/输入时应该怎样处理。Profile 指导评测，不会增加工具、改变系统提示
或修改已保存的 Case。

### `evaluation/` — 可选支持文件

仅在 Profile 引用 schema 或 fixture 时需要，不强制存在，也没有必需的
`input-contract.json`。当前官方 KUMA 生成路径接受文本；结构化 schema 在本地能解析
不代表远端支持。原生映射仍由 agent.toml 和 binding 负责。

### 注册表和自动记录

`resources/registry.toml` 位于单元之外，保存路径、启用状态、adapting/ready 和 `case`
数量。生成完成登记 adapting，认证控制晋升，`run` 选择启用且 ready 的 Agent。

导入器还会**自动创建 `source-manifest.json`**，记录 GitHub URL 或规范化本地路径及
revision，以便复用导入结果。
它是 ABB 内部记录，不是 KUMA 要求的文件，也不需要用户准备。继续添加流程时保留它。

生成记录位于 `cache/onboarding/<unit-name>-<path-digest>/`：build-state.json 跟踪
可复用工作，各 attempt 保存计划、SDK 目录、steps 和 build-result.json。这些也是
自动记录，不是 Agent 源码。

## 4. 审核与校验配置

对照真实源码审核生成的入口、原生输入输出映射、依赖、凭据声明和模型/工具路由。LangGraph 检查 graph descriptor 和工厂；ACP 检查原生命令和会话配置。Profile 应描述实际工具、调用方必须提供的数据和限制。人工修改后运行接入校验器（以下为 Bash 示例）：

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/NN-name"), plugin))
PY
```

这会检查文件及 SDK 解析器，不执行 Agent；未提供目录上下文时，不验证实时策略目录。静态校验通过不等于运行通过。

## 5. 运行一个 local 冒烟 Case

在注册表中将新 Agent 设为 `enabled = true`，然后运行一个 Case。`local` 使用通用文字 Cases 和本地 Judge，不消耗 KUMA 后端额度，但被测 Agent 和 local Judge 仍可能调用付费模型；它不执行接入认证，也不提供 KUMA 行为评测结论。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

## 6. 使用 KUMA 评测

冒烟测试后，使用 KUMA 生成新的 Case、收集执行证据并获得 Judge 报告。该过程会调用配置的模型服务和 KUMA API。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

## 7. 查看结果

使用 `Result saved` 后打印的真实文件路径，打开完整 `View:` 地址并保持命令运行。Conversation 查看输入输出，Judge 查看问题，Timing 查看执行过程和 OTel 轨迹。执行完成与 Judge 判定分别看：`issue` 表示发现问题，`insufficient_evidence` 本身不是已证实的缺陷。

```bash
agentbench view results/suites/SUITE_ID/events.json
```

## 8. 认证接入

要让 `adapting` Agent 被 `run` 选中，保持启用并执行认证。认证会按注册表 Case 预算重新执行，不是审核已有评测产物。所有请求的 Cases 无调用错误完成后晋升为 `ready`，Judge 发现问题本身不阻止晋升。已 ready 的 Agent 不再次认证执行，后续测试用 `evaluate`。`agent add` 也可带 `-c`，但需已有有效的生成或人工接入文件，不会隐式启用 `-b`。

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
```

## 9. 结果、复跑与故障处理

Suite 计划、Cases 和事件保存在 `results/suites/SUITE_ID/`，详细执行产物通常位于 `results/observe/RUN_ID/`。以命令打印的路径为准。`--results-dir DIR` 选择 ABB 结果根目录；`evaluate --output DIR` 单独选择 SDK 产物目录。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view --results-dir results/my-run
```

`resume` 继续符合条件的未完成工作，`retry` 定位一个未完成 Case；`reuse` 复用已保存输入，重新执行并 Judge，保留原结果。Case 序号从 1 开始。网页的 Rerun this Case 和 Open reuse Suite 提供同样的操作。复跑期间保持所属进程运行，非安全或响应不明的请求不保证能恢复。

```bash
agentbench resume results/suites/SUITE_ID
agentbench retry results/suites/SUITE_ID --agent AGENT_ID --case 1
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 1
```

Export JSON 只导出快照，不打包全部轨迹或独立 HTML。保留 Suite 和引用的执行目录才有完整证据。清理前用 `agentbench clean --dry-run` 预览，正式归档前停止运行与查看器。

网页提示 Trace UI not built 时构建 `web/`；Docker 错误时用同一用户检查 `docker info`；SDK 导入错误时在 ABB 的虚拟环境中安装 SDK；模型/key 错误时检查服务、模型名称及 Shell 变量优先级；规划错误或 needs_input 时查看保存记录并补充真实信息。

[CLI 文档](cli.zh-CN.md) · [详细故障排查（英文）](../Troubleshooting.md)
