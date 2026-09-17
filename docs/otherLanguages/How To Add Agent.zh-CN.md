# 添加 Agent

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | 中文 | [한국어](How%20To%20Add%20Agent.ko.md)

按 **环境配置 → 执行添加命令 → 了解生成文件** 的顺序操作。用户或 coding agent
都可以使用同一流程。除非命令切换了目录，均在 ABB 仓库根目录执行。

## 1. 配置环境

### 安装 ABB 和宿主机依赖

先完成 [ABB 安装](README.zh-CN.md)。需要 Git、Python 3.10+ 和已激活的 venv；
认证还需要当前用户可访问的 Docker。然后安装所选 SDK 的宿主机验证依赖：

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

`sdk list` 应列出 `kuma`；执行 ABB 的同一用户运行 `docker info` 必须成功。
下载和配置生成不要求 Docker，`-c` 认证需要。宿主机与评测容器中的 SDK 安装相互独立。

### 配置凭据和模型

只有在 `.env` 不存在时才复制模板：

```bash
test -f .env || cp .env.example .env
```

在本地编辑：

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key**：查询策略目录、生成 Case 和 Judge 所需。ABB 也接受
  `DEFUZEX_API_KEY`，非空 `KUMA_API_KEY` 优先。
- **OpenRouter key 和模型**：用于生成接入文件及运行 Agent。生成模型必须支持
  **严格结构化输出**；普通聊天可用不代表适合生成配置。示例模型名称不是代码的默认值。
- **Agent 依赖**：按目标仓库的说明准备工具 key、数据和外部服务。安装数据库驱动
  不会启动数据库；下载 Agent 也不会自动部署它依赖的全部服务。

凭据获取链接见 [中文配置说明](Guide.zh-CN.md#配置真实评测)。Shell 导出的变量优先于
`.env`，`--env-file PATH` 可选择其他文件。CLI 按声明解析凭据，不把整份 `.env`
挂进容器。不要把真实 key 写进源码或生成的配置文件。

### 按需准备网页

浏览器界面需要 npm，以及 Node.js **20.x 至少 20.19，或 22.12+**：

```bash
cd web
npm ci
npm run build
cd ..
```

这构建的是 ABB 查看器，不会安装 Agent 自己的浏览器或 Node/MCP 依赖。
不需要网页时，在下面的添加命令加 `--no-view`；无界面执行不要求 Node 或 `web/dist`。

## 2. 执行添加命令

把 URL 换成 Agent 的 GitHub 仓库地址，不使用文件或 `/tree/branch` 页面地址：

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`：生成并验证接入文件，将 Agent 登记为 `adapting`，不代表立即构建 Docker 镜像。
- `-c`：通过认证流程构建并运行 Agent。配置的 Case 执行验收成功后变为 `ready`；
  Judge 仍可能报告行为问题。

ABB 会下载源码、规划接入、逐文件保存验证结果，再询问是否进行认证。生成和认证可能
产生费用。目前自动配置支持 **LangGraph**；其他框架需要先有相应适配器支持。

想先检查生成文件，去掉 `-c`：

```bash
agentbench agent add https://github.com/owner/repository -b
```

两个参数都不加时，`agentbench agent add URL` 只下载并列出配置文件，不生成接入配置，
也不注册可运行的 Agent。下载器记录默认分支的 revision，目前没有 `--revision` 参数。

| 参数 | 用途 |
| --- | --- |
| `--no-view` | 认证时不启动网页，结果仍保存。 |
| `--build-model MODEL` | 接入文件生成模型。 |
| `--model MODEL` | 认证时 Agent 使用的模型。 |
| `--answers answers.txt` | 用文本文件回答前一次规划的问题。 |
| `--with-observe` | 配合 `-b` 生成 observe 的原生输入提示。 |
| `--build-settings settings.toml` | 用 `[build]` 表覆盖生成配置。 |

生成模型优先级：`--build-model`、settings 的 `model`、`OPENROUTER_BUILD_MODEL`、
`OPENROUTER_MODEL`。修改预算、超时或重试前，先看
[默认配置](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)。

## 3. 了解每个文件的用途

Agent 单元位于 `resources/agents/NN-name/`。命令在下载的源码外围生成接入文件，
不需要在运行命令前手写齐全。

```text
resources/agents/NN-name/
├── agent/                   # Downloaded upstream source
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 自身源码

保存下载的上游仓库。真实图、推理和工具仍在这里实现。ABB 接入文件放在目录外，
避免接入时悄悄替换原 Agent 的行为。

### `agent.toml` — ABB 如何启动和调用 Agent

声明 ID、框架、源码 revision、镜像构建/启动设置、适配器、输入输出映射、环境和
模型/工具路由。核对入口路径和必需输入。声明路由或变量不会实现工具，也不会启动服务。

### `bindings/*.py` — 原生输入输出与 ABB 的边界

导出同步、无参数的工厂，返回真实可调用 Agent，处理有源码依据的格式转换和生命周期
清理。不能编造答案或用简化 Agent 替代原实现。Python 语法有效不代表图能真正执行。

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

下载器还会**自动创建 `source-manifest.json`**，记录仓库和 revision 以复用下载。
它是 ABB 内部记录，不是 KUMA 要求的文件，也不需要用户准备。继续添加流程时保留它。

生成记录位于 `cache/onboarding/<unit-name>-<path-digest>/`：build-state.json 跟踪
可复用工作，各 attempt 保存计划、SDK 目录、steps 和 build-result.json。这些也是
自动记录，不是 Agent 源码。

## 生成之后

只使用 `-b` 时，准备与实际 binding 匹配的 JSON 输入，再检查原生执行并认证：

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

使用生成的 Agent ID。observe 不调用 KUMA Case/Judge，但模型/工具仍可能收费。
`evaluate --cases 1` 不改变注册表数量，certify 使用该数量，执行前要检查。
已 ready 的 Agent 不会再次认证；后续修改使用 evaluate 验证。

如果生成停止，读取 build-result.json 和失败步骤，修正后重跑相同的 `-b` 命令。
已完成文件保留并重新验证；人工文件冲突会停止，不会被覆盖。规划需要补充信息时使用
`--answers answers.txt`。

依赖、部署、Trace/Judge 或恢复问题见 [故障排查（英文）](../Troubleshooting.md)
和 [已知问题（英文）](../Documentation-Issue-Audit.md)。实现细节见
[开发者指南（英文）](../../agentbench/onboarding/build_agent_env/README.md)。
