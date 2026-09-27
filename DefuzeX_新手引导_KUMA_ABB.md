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
- 可以访问 DefuzeX、GitHub、PyPI、Docker Hub 和模型服务 API 的网络环境
- Python 3.10 或更高版本
- Docker
- 一个模型服务 API Key （deepseek glm 或者open router）
- 一个可用于注册 DefuzeX 的邮箱

以下命令默认在 macOS/Linux shell 中执行。

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

检查配置但不要打印 Key：

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

生成后检查：

```text
agent.toml
bindings/
Dockerfile
.dockerignore
requirement.md
evaluation/
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
resources/requirements/<agent-id>.md
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
