# 02 ReAct Agent

原仓库：https://github.com/langchain-ai/react-agent

固定版本：`9bbd82d84905acc37f527b1f372dae841016f3b4`。下载日期：2026-09-10。
`agent/` 是原版源码快照，内容未改。Git 元数据保留在本地忽略目录
`cache/upstreams/react-agent-9bbd82d.git`，避免将源码误提交为嵌套 submodule。

## 与 01 相同的结构

- `agent/`：完整上游源码、依赖和许可证。
- `agent.toml`：Docker、入口、Context、模型和工具流量配置。
- `Dockerfile`：Python 3.11、上游依赖、ABB worker、OTel，非 root 运行。
- `bindings/react.py`：处理输入输出和 Context；原版图使用 LangGraph 原生 checkpointer。
- `requirement.md`：能力与接入边界。
- `evaluation/`：SDK profile 和会话输入契约；选择服务目录中的 `basic-safety-research` (Research Information) 策略，题目仍由 SDK 生成。
- `smoke-input.json`：真实模型/搜索 smoke 的示例请求。

## 必需配置

在 ABB 的宿主环境或外部 dotenv 文件中提供：

- `OPENROUTER_API_KEY`：仅供 ABB interceptor 使用。
- `OPENROUTER_MODEL`：实际目标模型，需支持工具调用；也可通过 CLI `--model` 指定。
- `TAVILY_API_KEY`：真实搜索服务密钥，传给 Agent。

不需要给 Agent 放真实 `OPENAI_API_KEY`：ABB 会注入临时 token。
原版使用 `api.openai.com/v1/chat/completions`，拦截器负责目标模型/凭据替换。
`[adapter.context]` 当前为 `model="openai/gpt-4.1-mini"`、`max_search_results=5`；
前者选定原生客户端和请求模型，实际执行模型由 interceptor 决定。
系统提示词保持原版默认。生产环境不会替换 Tavily、吞掉搜索错误或伪造 trace provider。

## 输入与输出

接受 SDK 文本、`{"message":"..."}`，或原生 `{"messages":[...]}`。
互斥输入避免同时提交新消息与另一份历史。`messages` 是调用方当前请求的原生输入格式，
评测器不会自动回填旧消息。绑定返回最终回答 `answer` 和完整
`messages`；SDK 接收回答文本，raw output/trace 保留完整消息。

`evaluate` 在一个 Case 的容器中复用 adapter，每轮只传入当前 SDK Input。
该部署将上游原版 `builder` 编译一次，并配置 LangGraph 自带的 `InMemorySaver`；
运行时提供稳定的 `configurable.thread_id`。历史消息、工具调用与工具结果由原生
graph/checkpointer 保存，BBA 不拼接历史、不生成摘要、不实现额外记忆逻辑。
原版导出的 `graph` 本身未启用 checkpointer，这是明确的部署配置差异。

不同 Case 使用独立实例；同一 Case 结束时释放状态。不保证进程重启后的恢复，
也不自动压缩长上下文。独立 `observe` 仍为单次会话调用。

## 运行

在 AgentBehaviorBench 根目录执行：

```bash
python -m agentbench observe --list
python -m agentbench observe react-agent \
  --input resources/agents/02-react-agent/smoke-input.json \
  --env-file /path/to/host.env --model provider/model

python -m agentbench evaluate 02 --cases 2 --max-steps 4 --env-file /path/to/host.env \
  --result-output results/react-evaluation.json
```

`observe` 会真实调用模型和 Tavily；`evaluate` 还需要选定 SDK 的凭据及依赖。
上面的路径和模型是填写示例，不是内置默认值。

## 初始验收

历史初始接入状态为 `adapting`；当前参与状态以 `resources/registry.toml` 为准。
镜像依赖构建已完成。离线 Docker 测试使用 `--network none`，只在测试脚本中
提供假模型/搜索客户端，运行原版 ReAct 图与真实 ABB worker，检查工具循环、
原生 checkpoint、单 Case adapter 复用和 framework/OTel 产物。测试不构成真实模型/Tavily 认证。

```bash
.venv/bin/python -m pytest -q tests/test_issue39.py
```

历史真实多轮验收及 Judge 阻塞详情见 [MULTITURN-VALIDATION.md](./MULTITURN-VALIDATION.md)。
这些历史结果使用旧的历史回填方式，不能作为当前 checkpointer 配置的验收。

2026-09-14 当前配置的真实认证完成了三轮 Agent 调用：输入均为当前 SDK Input，
原生 checkpoint 消息数依次为 2、4、6；单次初始化、会话关闭和宿主 trace 校验正常。
官方 Judge 返回 `model_invalid_result`（`retryable=false`），未生成报告，因此仍为
`adapting`。这证明原生历史保留路径正常，不代表行为评测通过。详情及失败请求 ID
见[当前配置真实验收记录](../../../docs/Agent-Owned-Context-Live-2026-09-14.json)。

Case 数量、临时循环兼容、保存后导入及 wangyi 实现核对见 [BATCH-VALIDATION.md](./BATCH-VALIDATION.md)。

逐项需求完成状态和最后一次完整 CLI 结果见 [REQUIREMENTS-CHECK.md](./REQUIREMENTS-CHECK.md)。
