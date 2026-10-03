# DefuzeX Agent 接入新手指南

本指南面向参加 DefuzeX Agent 测试的开发者。你将从 GitHub Issue 认领一个外部 Agent，在 5 天内完成环境准备、ABB 接入、Pull Request、KUMA Evaluation 和 Trace 提交。

认领、进度更新、Credit 审批、PR 链接和最终结果都在你认领的同一个 GitHub Issue 中完成。不需要填写 Google Form 或其他登记表。

相关项目：

- [KUMA-DefuzeX](https://github.com/DefuzeX-AI/KUMA-DefuzeX)
- [AgentBehaviorBench（ABB）](https://github.com/DefuzeX-AI/AgentBehaviorBench)
- [KUMA SDK Guide](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/sdk-guide.md)
- [KUMA Runtime Trace](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/runtime-trace.md)
- [ABB Operation Guide](https://github.com/DefuzeX-AI/AgentBehaviorBench/blob/main/docs/Guide.md)
- [ABB Agent Onboarding Runbook](https://github.com/DefuzeX-AI/AgentBehaviorBench/blob/main/docs/How%20To%20Add%20Agent.md)

## 完整流程

```text
认领 GitHub Issue 中的 Agent
    -> 5 天内完成任务
    -> 安装 ABB，并在同一个 .venv 中安装 KUMA 依赖
    -> 注册 DefuzeX 并跑通 KUMA Free
    -> 在原 Issue 申请 50 KUMA Credits
    -> 将 Issue 中的 Agent 接入 ABB
    -> 提交 ABB Pull Request
    -> 完成 KUMA Official Evaluation
    -> 上传完整 KUMA Trace 和至少一条真实错误用例
    -> 在原 Issue 提交最终结果
```

## 开始前准备

你需要准备：

- GitHub 账号
- Git
- 可以访问 DefuzeX、GitHub、PyPI、Docker Hub 和模型服务 API 的网络环境
- Python 3.10 或更高版本
- Docker
- 一个模型服务 API Key （deepseek glm 或者open router）
- 一个可用于注册 DefuzeX 的邮箱

安装命令按 Windows PowerShell、macOS 和 Linux 分别列出。后文未标注平台的 `bash` 代码块适用于 macOS/Linux 的 bash/zsh；PowerShell 设置环境变量使用 `$env:变量名 = "值"`，不能直接复制 `export`。跨行命令也可以合并成一行执行。

## 第 0 步：认领 GitHub Issue

维护者会提前发布一批公开 Issue。每个 Issue 都会提供一个外部 Agent 的源码 URL、任务要求和验收标准。

选择一个尚未被认领的 Issue，在评论区回复：

```text
认领状态：claimed
参与者：你的 GitHub 用户名
计划使用的模型：provider/model
```

维护者确认后，你有 5 天完成本指南中的全部步骤。超过期限仍没有完成时，任务可能会被释放给其他参与者。如果遇到阻塞，请在同一个 Issue 中说明原因。

不要在 Issue 中发布 API Key、Cookie、`.env` 内容、原始用户数据或未脱敏 Trace。

## 环境安装：ABB 与 KUMA（第 1 步前完成）

先安装 ABB 和 KUMA，再执行后面的 `kuma whoami`、`kuma quickstart`、Agent 接入和评测。**ABB 与 KUMA 必须安装在运行 ABB 的同一个 Python 虚拟环境中。**

`python -m pip install -e .` 只安装 ABB 在 `pyproject.toml` 中声明的依赖，不会自动安装 KUMA。下面的 `python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt` 才会安装 KUMA 插件所需的发行包及 OpenTelemetry 依赖；安装一次即可，无需另外 clone KUMA 仓库。

根据你的系统选择一组命令。如果已经 clone ABB，请直接进入已有的 `AgentBehaviorBench` 目录；如果已有可用的 `.venv`，请激活它后执行两条安装命令，无需重新 clone 或创建环境。

### Windows：PowerShell

先安装 Git 和 Python 3.10+，确认 PowerShell 中可以运行 `git --version` 和 `python --version`。然后执行：

```powershell
git clone https://github.com/DefuzeX-AI/AgentBehaviorBench.git
cd AgentBehaviorBench

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
```

执行 `pip install -e .` 时必须在 ABB 仓库根目录，也就是含有 `pyproject.toml` 的目录，不能停留在它的父目录。

如果 PowerShell 禁止执行 `Activate.ps1`，可以直接使用虚拟环境中的解释器，无需修改执行策略：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
```

采用这种方式时，后续 `python` 命令使用 `.\.venv\Scripts\python.exe`，`kuma` 命令使用 `.\.venv\Scripts\kuma.exe`，以确保使用同一个环境。新打开终端时也需重新激活环境或使用完整路径。虚拟环境用法可参考 [Python venv 文档](https://docs.python.org/3/library/venv.html)。

Docker Agent 的认证和评测还需要启动 [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)，使用 WSL 2 后端及 Linux 容器。在 WSL 的 Linux 终端中运行 ABB 时，改用下方 Linux 命令，并在 WSL 内创建自己的 `.venv`，不要复用 Windows 的 `.venv`。原生 PowerShell 的安装与离线示例已验证，Docker Agent 仍需按其依赖检查。

### macOS：Terminal（zsh/bash）

先安装 Git 和 Python 3.10+，确认 `git --version` 和 `python3 --version` 可用。然后执行：

```bash
git clone https://github.com/DefuzeX-AI/AgentBehaviorBench.git
cd AgentBehaviorBench

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
```

Docker Agent 的认证和评测还需要启动 [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)。下载时选择与你的 Apple Silicon 或 Intel 芯片对应的版本；目标 Agent 的容器镜像也必须支持你的 CPU 架构。

### Linux：Terminal（bash/zsh）

先安装 Git 和 Python 3.10+，并确认 Python 提供 `pip` 和 `venv`。如果创建虚拟环境时报缺少 `venv` 或 `ensurepip`，先通过发行版的软件包管理器安装与当前 Python 版本匹配的 venv 支持包，再重试。

```bash
git clone https://github.com/DefuzeX-AI/AgentBehaviorBench.git
cd AgentBehaviorBench

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
```

Docker Agent 的认证和评测还需要按发行版安装并启动 [Docker Engine](https://docs.docker.com/engine/install/)。确保运行 ABB 的同一个用户能执行 `docker info`；不要用 `sudo pip` 把 ABB 或 KUMA 安装到系统 Python 中。

### 所有平台：验证安装

以下命令在 ABB 仓库根目录、已激活的 `.venv` 中执行，不需要 API Key：

```text
python -c "import sys; print(sys.executable)"
python -m agentbench --help
python -m agentbench sdk list
kuma --help
python -c "from kuma import KumaClient; from kuma.evidence.runtime_contract import derive_casegen_evidence_capabilities; print('KUMA dependencies OK')"
python -m examples.offline_demo --output results/offline-demo.json
```

第一条命令应显示本次使用的 `.venv` 里的 Python 路径。`sdk list` 应列出 `kuma` 和 `local`，但仅列出插件名称不能证明 KUMA 依赖已安装，因此还要完成 KUMA 导入检查。

离线示例无需 Docker、模型服务或 KUMA API Key。预期显示 `Case execution: 1/1 completed | Judge: pass=1` 和 `exit_code=0`。保存 `OFFLINE_RESULT=` 后打印的实际结果路径；文件名会自动添加时间戳。这个示例只验证本地运行流程，后面仍需验证账号、模型和 Docker Agent。

开始 Docker Agent 的认证或评测前，在同一终端执行 `docker info`，确认 Docker 已启动且当前用户可访问。

### 可选：安装网页查看器

网页查看器还需要 npm，以及 Node.js 20.x 至少 20.19，或 22.12+。安装 Python 依赖不会自动安装这些工具。Windows、macOS 和 Linux 都可以在仓库根目录依次执行：

```text
cd web
npm ci
npm run build
cd ..
```

然后运行 `python -m agentbench view <OFFLINE_RESULT 实际路径>`，打开终端输出的完整 `View:` 地址，并保持命令运行。只使用命令行时可以跳过网页构建，在支持该选项的运行命令中使用 `--no-view`。

## 第 1 步：注册 DefuzeX 账号

### 创建账号

1. 打开 [DefuzeX 登录页](https://defuzex.ai/login)。
2. 点击 **Sign up**。
3. 填写 Email、Password 和 Confirm Password。
4. 点击 **Continue**。
5. 也可以使用 **Continue with Google** 注册或登录。

请使用你能长期访问的邮箱，不要在 Issue、PR 或 Trace 中公开密码和验证码。

### 获取 KUMA API Key

登录后进入 [Dashboard API Keys](https://defuzex.ai/dashboard/api-keys)，创建一枚本地测试用 API Key 并立即保存。KUMA Key 通常以 `dfx_` 开头。

macOS/Linux：

```bash
export KUMA_API_KEY="dfx_..."
```

Windows PowerShell：

```powershell
$env:KUMA_API_KEY = "dfx_..."
```

不要把真实 Key 提交到 Git。如果 Key 泄露，请在 Dashboard 中撤销并重新创建。

验证账号：

```bash
kuma whoami
kuma strategies list
```

验证失败时，把错误类型、HTTP 状态和 CLI 版本回复到 Issue，不要贴出完整 Key。

## 第 2 步：跑通 KUMA Free 和 Example Agent

`Free` 表示不消耗 KUMA Credit，但模型 API 调用仍可能产生费用。

### 检查 KUMA SDK

```bash
kuma quickstart
```

### 检查 ABB

```bash
python -m agentbench --help
python -m agentbench sdk list
```

如果仓库提供 Offline Demo，可以运行：

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

### 配置模型服务

#### 最简单的方式：复制 `.env.example`，填写 API Key

在 ABB 仓库根目录，把 `.env.example` 复制成 `.env`，然后用编辑器打开 `.env`，填写对应的 API Key 和模型名称即可。如果已经有 `.env`，直接编辑已有文件，不要覆盖原配置。

Windows PowerShell：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

macOS/Linux：

```bash
test -f .env || cp .env.example .env
```

默认使用 OpenRouter，在 `.env` 中找到并填写以下字段：

```dotenv
OPENROUTER_API_KEY=你的 OpenRouter API Key
OPENROUTER_MODEL=openai/gpt-4.1-mini
KUMA_API_KEY=你的 KUMA API Key
```

模型名称可以换成账号可用的模型；后续使用 `agent add -b` 生成接入配置时，生成模型需要支持严格结构化输出。目标 Agent 需要其他工具服务时，再填写模板中的对应字段。

ABB 的 Agent 接入和评测命令会自动读取项目根目录的 `.env`，使用这种方式后无需再执行下面的 `export`。终端中已设置的环境变量优先于 `.env`；如果修改文件后仍使用旧配置，请清除终端中的旧变量或在新终端激活 `.venv` 后重试。不要提交包含真实 Key 的 `.env`。

#### 可选方式：在终端设置环境变量

也可以不使用 `.env`，改为在当前终端设置变量。以下示例使用 macOS/Linux 的 `export`；Windows PowerShell 使用 `$env:变量名 = "值"`。

默认使用 OpenRouter：

```bash
export OPENROUTER_API_KEY="你的 OpenRouter API Key"
export OPENROUTER_MODEL="openai/gpt-4.1-mini"
```

没有 OpenRouter 时，可以使用支持 OpenAI 兼容接口的 GLM 或 DeepSeek。ABB 当前仍使用 `OPENROUTER_*` 变量名，但可以把 `OPENROUTER_BASE_URL` 指向其他服务；不要设置 `ABB_MODEL_PROVIDER=glm` 或 `ABB_MODEL_PROVIDER=deepseek`。

GLM：

```bash
export OPENROUTER_API_KEY="你的 GLM API Key"
export OPENROUTER_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export OPENROUTER_MODEL="你的 GLM 模型 ID"
```

如果使用智谱 Coding Plan，请以控制台提供的地址为准，例如：

```bash
export OPENROUTER_BASE_URL="https://open.bigmodel.cn/api/coding/paas/v4"
```

DeepSeek：

```bash
export OPENROUTER_API_KEY="你的 DeepSeek API Key"
export OPENROUTER_BASE_URL="https://api.deepseek.com"
export OPENROUTER_MODEL="deepseek-v4-flash"
```

需要更强推理能力时，可以改成账号当前可用的 `deepseek-v4-pro`。模型 ID 以服务商控制台为准。

如果采用终端环境变量方式，可以检查当前终端的配置，但不要打印 Key（这里只检查 shell 变量，不会读取 `.env`）：

```bash
test -n "$OPENROUTER_API_KEY" && echo "API key is set"
echo "base_url=${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}"
echo "model=$OPENROUTER_MODEL"
```

### Example Agent Local Smoke

```bash
agentbench evaluate <example-agent-id> \
  --cases 1 \
  --sdk local \
  --no-view
```

`--sdk local` 不消耗 KUMA Credit，但 Agent 和 Local Judge 仍可能调用模型服务。

完成后，在原 Issue 中简要说明账号和基础命令已通过，并直接粘贴 ABB 自动生成的 `evaluation/manifest.json`。不要手工编造或改写 JSON 内容：

```text
状态：kuma-free-passed
kuma whoami / kuma quickstart / ABB sdk list：passed
模型：provider/model
结果路径或 run-id：
结果文件：evaluation/manifest.json
```

然后粘贴该文件的实际内容：

```json
{
  "run_id": "实际 run_id",
  "case_id": "实际 case_id",
  "phase": "finished",
  "execution": "succeeded",
  "otel": "complete",
  "submission": "committed",
  "judge": "received",
  "evidence": "captured"
}
```

上面 JSON 仅用于展示字段形式，提交时必须使用结果目录中的原文件；如果原文件包含 Prompt、用户数据或其他敏感信息，先脱敏后再粘贴，并同时保留完整文件路径供维护者查看。

## 第 3 步：申请 50 KUMA Credits

完成 KUMA Free 和 Example Agent Local Smoke 后，在原 Issue 中回复：

```text
状态：credit-requested
DefuzeX 用户名：
DefuzeX 邮箱：
申请额度：50 credits
```

维护者会在同一个 Issue 中回复是否批准免费 Credit。收到明确批准前，不要运行可能消耗额度的正式 KUMA Evaluation。

## 第 4 步：将 Issue 中的 Agent 接入 ABB

从 Issue 正文复制 Agent 源码 URL。不要把 GitHub Issue URL 当成 Agent 源码 URL。

### 导入源码

```bash
python -m agentbench agent add <Agent 源码 URL>
```

确认源码、入口、依赖、工具和外部服务需求与 Issue 中的描述一致。导入源码不等于 Agent 已经接入 ABB。

### 生成 ABB 配置

```bash
python -m agentbench agent add <Agent 源码 URL> \
  -b \
  --sdk kuma \
  --no-view
```

这一步只生成接入配置，不会执行认证。Windows PowerShell、macOS 和 Linux 都可以使用同一条单行命令：

```text
python -m agentbench agent add <Agent 源码 URL> -b --sdk kuma --no-view
```

ABB 会发现源码入口，用模型规划并逐个生成文件，每个文件通过静态校验和源码兼容性审查后再保存；审查发现输入解析、原生调用流程或配置不一致时，会反馈给模型修正。只有全部配置通过，才会显示 `Build status: generated` 并登记为 `adapting`。这仍需要后续真实运行验证。

如果模型需要查看已克隆仓库中的具体源码文件，ABB 会在明确的文件数量和字节预算内自动补充证据，无需你手工粘贴源码。缺少实际业务参数、部署地址或工具访问策略时，才需要提供相应事实。

复杂项目可以用 `--build-model <模型 ID>` 显式指定配置生成模型，也可以在 `.env` 设置 `OPENROUTER_BUILD_MODEL`。这与目标 Agent 执行时使用的模型分别配置。更换生成模型会重新规划并审查已有文件，文件仍会保留。

LangGraph 项目没有 `langgraph.json` 时，可以通过外层 binding 调用源码中真实的 Python 工厂，不需要手工补一个不存在的描述文件。ABB 直接调用 binding，不会先运行上游 CLI，因此 binding 必须实现实际需要的输入转换、初始化和资源管理。

如果某一步失败，可以重新运行同一条命令继续；完成的文件会保留。`needs_input` 表示仍缺少具体事实，`conflict` 表示现有文件与接入要求冲突且已保留，请按终端说明处理。生成过程使用 `.env` 中配置的模型服务，会消耗模型服务额度。

生成后检查：

```text
agent.toml
bindings/
Dockerfile
.dockerignore
requirement.md
evaluation/（仅当 SDK 和输入契约需要额外 schema 时）
```

确认运行入口、输入输出映射、Docker 构建、模型路由、工具依赖和上游 Agent 版本来源都正确。你不需要修改上游 Agent 或创建新的 Agent commit。目录中不能包含 `.env`、API Key、用户数据或缓存。

当前 ABB 自动配置流程主要支持 LangGraph。其他框架如果不能通过适配器运行，请在 Issue 中说明，不要把它伪装成 LangGraph。

### Local Smoke

```bash
agentbench evaluate <agent-id> \
  --cases 1 \
  --sdk local \
  --no-view
```

Local Smoke 必须在 Docker 中完成。把结果路径或 run-id 回复到原 Issue。

## 第 5 步：提交 ABB Pull Request

Local Smoke 通过后，向 [AgentBehaviorBench](https://github.com/DefuzeX-AI/AgentBehaviorBench) 提交 Pull Request。

PR 至少包含：

```text
resources/agents/NN-agent-name/
resources/agents/NN-agent-name/agent
resources/agents/NN-agent-name/requirement.md
resources/agents/NN-agent-name/agent.toml
resources/agents/NN-agent-name/Dockerfile
resources/agents/NN-agent-name/bindings/*.py
resources/registry.toml
必要的 tests/
Agent 来源、版本（如 tag 或 commit）、License
原 GitHub Issue URL
使用的模型和运行命令
Local Smoke 结果
```

PR 不应包含 `.env`、API keys、原始用户数据、完整运行缓存、`.venv`、Docker secrets 或大型临时文件。

将 PR URL 回复到原 Issue。完整 Trace 不要提交到代码仓库。

## 第 6 步：运行 KUMA Official Evaluation

PR 已提交并且 Credit 已批准后，运行：

```bash
agentbench evaluate <agent-id> \
  --cases 1 \
  --sdk kuma \
  --no-view
```

如果需要 Certification：

```bash
agentbench certify <agent-id> \
  --sdk kuma \
  --no-view
```

正式运行必须至少包含一条真实错误用例。真实错误用例指 Agent 在真实任务输入下实际产生的错误，例如工具调用失败、输入映射错误、依赖服务错误、输出不符合任务要求，或 Judge 识别到可复现的行为问题。

不能通过手工修改 Trace、伪造错误响应或简单断网来制造错误用例。正常通过用例和错误用例都要保留。

在原 Issue 中记录错误用例：

```text
Case ID 或输入：
错误发生步骤：
Agent/工具输出：
Trace 路径：
Judge 结果：
是否可以复现：
```

`Judge issue` 不一定代表 ABB 接入失败；请同时记录 Agent 执行状态、Trace 状态和 Judge 结果。

## 第 7 步：上传完整 KUMA Trace

最终提交的 Trace 状态必须是 `complete`，并且至少包含一条真实错误用例。`partial` 或 `missing` 只能作为排查问题的中间结果，不能作为最终交付。

ABB/KUMA 会自动生成运行结果目录。不同版本的目录和文件名可能不同，请以终端输出的 `Result saved` 或 `Result artifact` 路径为准。不要手工创建或修改这些 JSON 文件。

常见文件包括：

```text
run.json
network.jsonl
egress.jsonl
evaluation/
  manifest.json
  case.json
  inputs/
  judge/
    report.json
  sdk.jsonl
```

这些文件通常由 ABB/KUMA 自动生成：

| 文件 | 作用 |
|---|---|
| `run.json` | ABB 宿主侧运行状态 |
| `network.jsonl` | 模型和工具请求的 Trace 记录 |
| `egress.jsonl` | 其他出网请求记录（如果有） |
| `evaluation/manifest.json` | KUMA/Local 执行和 Judge 状态摘要 |
| `evaluation/case.json` | 本次执行使用的 Case |
| `evaluation/inputs/` | 输入、输出、提交和证据 |
| `evaluation/judge/report.json` | Judge 报告 |

上传前检查并删除：

- API Key、Cookie 和 Token
- 用户隐私数据
- 不应公开的 Prompt、工具参数或文件路径
- 未公开的源代码或本地环境信息

如果压缩包可以作为 GitHub Issue 附件上传，就直接回复到原 Issue。文件较大时，使用维护者在 Issue 中指定的受控存储，并把链接回复到同一个 Issue。

最终在 Issue 中回复：

```text
状态：trace-submitted
上游 Agent 版本（如有）：
ABB PR：
KUMA run-id：
Trace 文件或链接：
Trace 状态：complete
真实错误用例：Case ID / 错误步骤 / Judge 结果
是否已脱敏：yes
已知问题：
```

## 完成标准

- [ ] 已在 GitHub Issue 中认领 Agent
- [ ] 在 5 天期限内完成，或已在 Issue 中获得延期
- [ ] DefuzeX 账号和 KUMA API Key 可用
- [ ] `kuma quickstart` 成功
- [ ] Example Agent Local Smoke 成功
- [ ] 50 KUMA Credits 已在 Issue 中批准
- [ ] 外部 Agent 已接入 ABB
- [ ] ABB Local Smoke 成功
- [ ] ABB Pull Request 已提交，并关联原 Issue
- [ ] KUMA Official Evaluation 已完成
- [ ] 最终 Trace 状态为 `complete`
- [ ] Trace 至少包含一条真实错误用例
- [ ] Trace 已脱敏
- [ ] 所有结果链接和状态已回复到原 Issue

## 常见问题

### Free 是否完全免费？

`kuma quickstart` 不消耗 Credit，也不调用模型。ABB 的 `--sdk local` 不消耗 KUMA Credit，但 Agent 和 Local Judge 仍可能产生模型 API 费用。正式 `--sdk kuma` 需要经过 Credit 批准，并可能产生 KUMA 服务消耗。

### 本地运行成功，但 Docker 失败怎么办？

ABB 的验收以 Docker 中的结果为准。本地缓存、全局依赖和 `.env` 不会自动进入容器。请把 Docker 错误、上游 Agent 版本（如有）和结果路径回复到 Issue，不要修改结果来绕过检查。

### Trace 只有 partial 怎么办？

不要把 partial Trace 作为最终交付。检查 Agent 是否在同一进程中产生 OTel spans、是否存在跨进程或子容器调用，以及是否发生导出失败。修复后重新运行，并在 Issue 中说明新旧结果的关系。

### Judge 返回 issue 是不是接入失败？

不一定。Agent 可能已经正常启动并完成请求，但 Judge 发现输出不符合 Case。请分别记录 Agent 执行状态、Trace 状态和 Judge 结果，不要为了得到 pass 而删除错误用例。

### 没有 OpenRouter 怎么办？

可以使用支持 OpenAI 兼容接口的 GLM 或 DeepSeek，并设置 `OPENROUTER_BASE_URL`、`OPENROUTER_API_KEY` 和 `OPENROUTER_MODEL`。具体配置见“第 2 步：配置模型服务”。
