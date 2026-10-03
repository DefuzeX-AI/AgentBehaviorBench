# LangGraph binding 编写手册

[English](../LangGraph%20Bindings.md) | 中文

[添加 Agent](How%20To%20Add%20Agent.zh-CN.md) · [Agent 单元](Agents.zh-CN.md)

本手册说明 ABB 的 LangGraph Agent 单元中，`bindings/` 里的 Python 文件具体如何编写。Binding 负责加载真实 Agent，把当前输入转换成原生接口需要的格式，保留执行配置，返回真实结果，并释放自身拥有的资源。编写时必须依据原生应用的实际调用流程，包括公开调用者在执行前完成的初始化。

下文的接口说明来自 ABB 当前的 loader 和 adapter；编写约定用于保留原生应用行为。静态校验通过，不代表真实执行正确或观测证据完整。原生 ACP 接入使用协议配置，不适用这里的 Python binding 接口。

## 文件放在哪里以及如何选中入口

```text
resources/agents/NN-name/
  agent.toml
  agent/                       # 导入的源码及原有资源
  bindings/
    bridge.py                  # agent.toml 选中的工厂文件
  Dockerfile
  .dockerignore
  requirement.md
```

可以使用 `bridge.py` 或 `research_bridge.py` 等有明确用途的文件名。下面这段 adapter 配置选中 `bindings/bridge.py:create_graph`：

```toml
[adapter]
type = "langgraph"
mode = "in_process"
binding = "bridge.py:create_graph"
input_key = "message"
```

这只是 manifest 中的一部分，不是完整的 Docker 部署配置。`binding` 相对于外层 `bindings/`，不要写成 `bindings/bridge.py:create_graph`。当前配置读取器允许在直接加载 binding 时，同时省略 `config` 和 `graph_id`。TOML 没有 null 值，应省略字段，不能写 `config = null`。

如果原生源码已有合适的 graph 描述文件，保留它的实际路径和 graph 名称：

```toml
config = "langgraph.json"
graph_id = "agent"
```

这两行放在 `[adapter]` 下。`config` 相对于 `agent/`；JSON 的 `graphs` 中必须声明所选名称。配置了 `binding` 时，ABB 实际加载的是外层 binding，graph JSON 不会自动完成原生应用的初始化。接入文件应放在导入的源码目录外。

## ABB 实际会调用什么

```text
当前 Case 输入
  -> adapter 输入映射
  -> binding.invoke(value, config=...) 或 await binding.ainvoke(...)
  -> 原生应用
  -> binding 返回结果
  -> adapter 输出映射，并保留 raw_output
```

### Case 的输入怎样进入 binding

**ABB 不会把整个 Case 传给 `create_graph()`。它先创建 Agent 实例，再把 Case 中每一步的输入传给 `invoke()` 或 `ainvoke()`。** Binding 返回结果后，ABB 负责将结果提交给 SDK；binding 自身不需要调用 SDK 的提交接口。

假设一个对话型 Case 有两步：

```text
第 1 步：研究 OpenAI
第 2 步：重点补充它的产品信息
```

下面是便于理解的调用示意。假设 binding 提供 `ainvoke` 和 `aclose`；暂时省略 adapter 映射、观测配置和 SDK 提交的具体实现：

```python
# 同一个 Case 创建一个 Agent 实例
agent = create_graph()
config = {
    "configurable": {"thread_id": "case-session-001"}
}

try:
    # 第一步：传入当前输入
    result1 = await agent.ainvoke(
        "研究 OpenAI",
        config=config,
    )
    # ABB 将 result1 提交给 SDK

    # 第二步：继续使用同一个实例和会话 ID
    result2 = await agent.ainvoke(
        "重点补充它的产品信息",
        config=config,
    )
    # ABB 将 result2 提交给 SDK
finally:
    # Case 完成或执行失败后清理资源
    await agent.aclose()
```

原生对象只有同步 `invoke` 时，ABB 在线程中调用它；只有同步清理 `close` 时，ABB 调用 `close`。这份示意用于理解顺序，不是要在 binding 里实现一个 Case 调度器。

### Adapter 怎样包装当前输入

真实调用中，adapter 位于 SDK 输入和 binding 之间。如果 `agent.toml` 配置：

```toml
[adapter]
input_key = "message"
```

这只是用于解释映射的一段配置，其余 adapter 字段沿用前面的完整表。SDK 提供文字 `"研究 OpenAI"` 时，ABB 传给 binding 的值变成：

```python
await agent.ainvoke(
    {"message": "研究 OpenAI"},
    config=config,
)
```

于是，binding 中的处理可以理解为：

```python
async def ainvoke(self, value, config=None):
    # value 是当前这一步输入；这里假设字段已通过校验
    text = value["message"]

    # 转换成真实 LangGraph 需要的 state
    state = {
        "messages": [{"role": "user", "content": text}]
    }

    # 调用真实 Agent，并把结果返回给 ABB
    return await self._graph.ainvoke(state, config=config)
```

这段假设原生 graph 接受 `messages`，完整的输入校验见后文模板。返回值经 adapter 的 `output_key` 处理后，由 ABB 提交给 SDK，同时保留 `raw_output`。传入本来就是字典时，adapter 不会再次包装。

- Case 的当前输入进入 `value`。
- 会话和追踪等执行配置进入 `config`。
- `create_graph()` 只负责创建实例，不接收 Case。
- ABB 每次只传当前一步，不自动附带历史；历史由原生 Agent 已有的会话或 checkpoint 管理。无状态 Agent 不会因为复用实例就自动获得对话记忆。

### 函数接口对照

| 导出函数或方法 | 应实现的行为 |
| --- | --- |
| `def create_graph()` | 没有装饰器、可无参调用的同步工厂。返回有可调用 `invoke` 的对象，不能返回协程或生成器。 |
| `def invoke(self, value, config=None)` | 执行一次输入并返回约定的最终结果。即使原生应用只能异步执行，也需要提供这个接口。 |
| `async def ainvoke(self, value, config=None)` | 同步应用可不提供；异步执行应实现。返回最终结果，不能通过 yield 输出事件。 |
| 仅关键字参数 `context=None` | 配置了 `[adapter.context]` 时接收它，并按原生 API 转成其支持的上下文类型。 |
| `close()` 或 `aclose()` | 释放实例自身拥有的资源，支持重复清理和部分初始化后的清理。 |

在 adapter 层，参数名是 `run_config`；调用 binding 时，ABB 把它传成 `config`。函数签名能接收这个参数，只解决了接口兼容问题；内部原生调用是否保留它，需要另行检查。ABB 异步 adapter 优先调用 `ainvoke`，没有时在线程中执行 `invoke`。如果原生同步 API 只能在主线程运行，需要明确实现兼容的执行方式，不能直接依赖自动线程转发。

Docker worker 的观测 callbacks 在容器进程内创建。宿主机 callback 对象不能通过 JSON 请求传进另一个进程。Binding 收到的是 worker 内可直接使用的配置，不能把它序列化。

## 写文件前先确认原生调用约定

阅读真正运行该 Agent 的 CLI、应用或示例，把下列事实写进模块说明，并用它们指导实现：

| 要确认的问题 | 从源码中寻找的证据 |
| --- | --- |
| 公开入口是什么 | 确切模块、工厂或类、构造参数，以及执行方法。 |
| 一次输入需要什么 | 必需业务字段、接受的类型，以及调用者构造的初始 state。 |
| 执行前需要做什么 | 模型客户端、硬件配置、数据集、目录、数据库或会话。 |
| 怎样判断完成 | 最终报告、消息或 state，以及公开调用者判断失败的条件。 |
| 执行配置如何进入原生应用 | 原生 `config` 参数，或已验证的框架配置上下文机制。 |
| 同一个 Case 中哪些内容保留 | 原生 checkpoint、session、workspace 和资源所有权。 |

ABB 直接调用 binding，不会自动运行上游 CLI。CLI 原本完成的 JSON 解析、state 构造、服务启动和可写路径准备，不能留在 CLI 中等它自动发生。Binding 应复现必要的公开生命周期，推理和工具仍由真实 Agent 实现。必需业务输入或部署选择不明确时，在 onboarding 中说明缺什么，不能凭空补值以便加载成功。

## 选择最小的兼容实现

### 直接返回原生 Agent

只有原生对象已经接受 adapter 输入、支持 `config`、返回所需结果，并能管理自身资源时，才使用这种写法。例如 Folder Mover 当前的原生对象接受文字或严格的 `{"message": text}`，并提供调用与清理方法：

```python
"""Expose folder_mover's public Agent without changing its input or lifecycle."""


def create_graph():
    """Return a fresh native Agent; input example: {'message': 'Explain your tool'}."""
    from folder_mover import create_graph as native_create_graph
    return native_create_graph()
```

这个实例需要 worker 中已有 Folder Mover 源码、依赖和正确的导入路径。如果原生编译图需要 `{"messages": [...]}`，而 SDK 提供文字或 `{"message": text}`，就不能原样返回图。`input_key = "message"` 不会把这个字段变成 `messages`。

### 把文字转换成原生 graph state

下面的模板假设：已确认的原生工厂返回可同步调用的图，输入是 `messages`，应保留完整返回值，实例拥有的清理接口是 `close`。使用前，将 `upstream_agent.graph` 和工厂名替换为从源码确认的真实 API。如果这些前提不成立，应按原生生命周期实现，而不是照抄模板。

```python
"""Translate one current message to native messages state.

Input: text or exactly {'message': nonempty_text}.
Config: forwarded unchanged to the native graph.
Output: the complete native result, without an output_key extraction here.
Errors: invalid input and native failures propagate.
Ownership: this instance owns the graph returned by the native factory.
"""
from collections.abc import Mapping


def state_from_input(value):
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply exactly one message field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("message must be a non-empty string")
    return {"messages": [{"role": "user", "content": value}]}


class AgentGraph:
    def __init__(self):
        from upstream_agent.graph import create_graph as create_native_graph
        self._native = create_native_graph()

    def invoke(self, value, config=None):
        if self._native is None:
            raise RuntimeError("Binding is closed")
        return self._native.invoke(state_from_input(value), config=config)

    def close(self):
        native, self._native = self._native, None
        close = getattr(native, "close", None)
        if callable(close):
            close()


def create_graph():
    """Return a fresh binding; example input: {'message': 'Explain this text'}."""
    return AgentGraph()
```

原生调用和资源能安全在线程中运行时，ABB 异步 adapter 可以驱动这个同步模板。原生图同时支持同步与异步执行时，用下面的方法替换 `AgentGraph` 内的调用和清理方法，保留原构造函数、输入转换函数和工厂：

```python
def invoke(self, value, config=None):
    if self._native is None:
        raise RuntimeError("Binding is closed")
    return self._native.invoke(state_from_input(value), config=config)


async def ainvoke(self, value, config=None):
    if self._native is None:
        raise RuntimeError("Binding is closed")
    return await self._native.ainvoke(state_from_input(value), config=config)


def close(self):
    native, self._native = self._native, None
    close_native = getattr(native, "close", None)
    if callable(close_native):
        close_native()


async def aclose(self):
    native, self._native = self._native, None
    close_native = getattr(native, "aclose", None)
    if callable(close_native):
        await close_native()
    else:
        close_native = getattr(native, "close", None)
        if callable(close_native):
            close_native()
```

将这些方法缩进到类内部。ABB 异步清理优先使用 `aclose`；客户端拥有异步资源时，需要走异步清理路径。不能用同步 `close` 丢弃本来需要 await 清理的资源。

如果图包含只能异步执行的节点，应提供 `ainvoke`，同步桥接仅在调用者没有运行中的事件循环时执行 `asyncio.run(self.ainvoke(value, config))`。不能在 `ainvoke` 中调用 `asyncio.run`。绑定到某个事件循环的客户端，可能无法跨多次新建事件循环复用；初始化和清理方式应符合原生库的要求。

## 保留 config 并区分 context

原生 API 支持时，直接传 `config=config`。其中可能包含 callbacks、tags、metadata、`configurable.thread_id` 和执行限制。它不是业务输入；`configurable` 也不能当成原生运行时 context。

明确的部署配置需要补充默认递归限制时，可以合并，但不要修改传入对象：

```python
run_config = dict(config or {})
run_config.setdefault("recursion_limit", 50)
result = await self._native.ainvoke(state, config=run_config)
```

这里的限制值只是示例，不是所有 Agent 的推荐值。需要修改嵌套字典时先复制对应字典，保留无关字段，不要每次调用都用随机 ID 覆盖 ABB 提供的 Case thread 身份。保留原有 callback 对象，不能 deepcopy 或 JSON 序列化整份配置。

原生 API 支持 context schema 时，用单独的关键字参数接收，并构造原生类型。例如当前 ReAct binding 接收 `context=None`，在 `config=config` 之外，额外传入 `context=Context(**dict(context or {}))`。凭据应通过声明的环境变量提供，不应放进 context 配置。

公开执行方法没有 `config` 参数时，不要传一个它不支持的关键字，也不要为传配置而绕过必要的初始化、直接调用底层图。当前 TradingAgents 接入在 `propagate` 外使用已验证的 LangChain 机制：

```python
from langchain_core.runnables.config import set_config_context

with set_config_context(dict(config or {})) as invocation_context:
    final_state, decision = invocation_context.run(
        native.propagate, ticker, trade_date
    )
```

这里假设 `native` 已构造，ticker 和日期已校验。这段依赖目标环境安装的 LangChain 版本，不适用于所有库。没有兼容机制时，明确说明观测限制。转发了 config，也不等于所有原生工具和模型调用都会产生完整证据。

## 处理业务输入和流式工作流

`input_key` 只包装非 mapping 输入，字典等 mapping 原样传递。Binding 应验证自己支持的字段和类型，不能静默丢掉未知字段，不能用上一条 ticker 或日期补当前请求，也不能把包含 JSON 的字符串当成已经解析的字典。

当前 KUMA onboarding 流程使用文字 Case 输入，其中包含普通自然语言请求。Profile 写着“请发送 JSON”并不能保证 Case 的序列化格式。应把完整请求放入源码确认的问题、消息字段或 questions 列表，其他可选字段保留原生默认值。明确约定的 JSON 问题文档可以作为额外输入格式解析和校验，但不能要求所有文字 Case 都通过 `json.loads`。随后复现公开调用者的初始 state 构造。如果缺少必需业务参数，无法忠实转换，应报告不兼容，不能猜测补值。本地 Profile 能解析结构化声明，不等于远端 Case 服务支持它。

| 原生工作流 | Binding 需要完成什么 |
| --- | --- |
| 公司研究 | 校验公司和可选元数据，将它们传给 `Graph` 构造函数，再消费 `run(config)`。 |
| CAD 生成 | 调用 `get_default_initial_state()`，设置本次 `user_request`。 |
| 实验协议生成 | 加载已确定的硬件配置和知识，初始化尝试次数，使用原生异步执行。 |
| 数据分析 | 同时提供用户指令和真实 DataFrame，说明数据固定还是由调用者提供。 |
| 交易分析 | 先校验调用者明确提供的 ticker 和日期，再调用 `propagate`。 |
| GPT Researcher | 构造完整的原生 task，包括 `publish_formats`，然后执行真实研究团队。 |

原生公开方法是异步生成器时，需要在 `ainvoke` 中消费。当前 Company Research 接口的重要调用形状是：

```python
# NativeGraph is the verified upstream class, not a replacement implementation.
native = NativeGraph(company=company, job_id=job_id)
report = None
async for update in native.run(config):
    editor = update.get("editor") if isinstance(update, dict) else None
    if isinstance(editor, dict) and "report" in editor:
        report = editor["report"]
if not isinstance(report, str) or not report.strip():
    raise RuntimeError("Native workflow completed without its final report")
return {"report": report}
```

这是异步方法内部的片段，输入校验、可选元数据、资源清理和进度观测仍需依据真实应用实现。直接返回 `native.run(config)` 只会返回一个迭代器，不会把工作流执行到最终结果。

## 返回结果并保留失败语义

没有 `output_key` 时，ABB 将 binding 的整个返回值作为 output，并保留为 `raw_output`。设置 `output_key = "report"` 时，必须返回包含 `report` 的 mapping；ABB 抽取该字段作为 output，同时保留完整 mapping。返回字符串或只有 `messages` 的字典，与这个设置不兼容。

优先保留原生最终结果。如果部署明确需要将结果转换成文字，说明使用哪个原生字段，并保留必要的 state 或报告证据。完成条件应与原生公开应用一致：有的返回完整 state，有的要求非空最终报告或助手回复。不要凭空增加质量判定，也不要把中间工具结果当成最终交付物。

让原生执行异常向外传播，不能捕获后返回看似成功的 `{"answer": "发生了错误"}`。错误信息不能包含凭据。原生工具报错、被 Agent 处理并解释，与 binding 或 runtime 执行失败不同；应保留原生处理方式。

## 管理资源并保留原生会话行为

Worker 在同一个 Case 的多次输入之间复用同一个 Agent 实例，并提供稳定的 thread ID。它只传当前输入，不会替 Agent 拼接历史。应保留原生应用本来具有的会话行为，不能为了让无状态工作流记住前文而额外加入 transcript、checkpoint 或记忆机制。不同 Case 之间不能共享可变状态。

按原生 API 的要求，复用资源可以在实例初始化时准备，也可以首次调用时延迟初始化。异步启动需要保持工厂同步，在 `ainvoke` 中执行可等待的准备流程。明确实例拥有的客户端、数据库进程、连接和私有临时目录，并在关闭及初始化失败时释放。工厂返回前发生失败时，ABB 尚未拿到可清理的实例，需要构造函数或工厂自行清理已取得的资源。

打包的数据资源可以相对于 `__file__` 定位，例如 `Path(__file__).resolve().parents[1] / "agent" / "data" / "dataset.csv"`。生成文件写入明确配置的可写路径。修改工作目录会影响整个进程，应限制在隔离 worker 内，并在适当时恢复。私有临时文件不会自动成为长期保存的评测产物。

Docker 需要安装真实依赖，把 binding 复制到选定 Agent root 旁边。Worker 默认 `--agent-root /opt/agent`；`launch.workdir` 是进程工作目录，可以与 Agent root 不同。当前静态布局检查器按 `launch.workdir` 查找 binding，因此在 `/tmp` 执行、源码放在 `/opt/agent` 的布局可能被拒绝。遇到这种情况，应核对检查器与 worker 的实际规则；本手册没有修改检查器，也没有验证真实执行成功。

模型路由、工具路由以及必要的非 HTTP 服务路由由配置声明。必需的本地服务仍要由原生生命周期或 binding 启动，声明路由不会启动服务。不要在 binding 中安装依赖、绕过网络拦截或写入真实凭据。

## 仓库中的参考实例

这些链接用于查找实现方式，应同时阅读源码和 manifest。现有 binding 可能有限制，不应作为适用于所有 Agent 的模板。下表描述当前实现，不记录认证状态。

| 单元 | 可参考的实现或需要复核的地方 |
| --- | --- |
| [01 Folder Mover](../../resources/agents/01-folder-mover-agent/bindings/bridge.py) | 直接返回原生对象；实际输入校验在 `agent/folder_mover.py`。 |
| [02 Company Research](../../resources/agents/02-company-research-agent/bindings/company_research_agent.py) | 构造阶段的业务参数、消费异步流和提取最终报告。 |
| [03 ReAct](../../resources/agents/03-react-agent/bindings/bridge.py) | 文字/messages 转换、原生 context 与 config 转发。 |
| [04 Crypto Hedge Fund](../../resources/agents/04-ai-hedge-fund-crypto/bindings/bridge.py) | 配置驱动的 portfolio 和市场 state；需复核未转发 config 的问题。 |
| [05 LabScript](../../resources/agents/05-labscript-ai/bindings/bridge.py) | 硬件 state 和只能异步执行的图；需复核 config 被替换的问题。 |
| [06 Multi Agent CAD](../../resources/agents/06-multi-agent-cad/bindings/bridge.py) | 原生默认 state 与递归配置合并。 |
| [07 Autoresearch](../../resources/agents/07-autoresearch-agents/bindings/bridge.py) | 计算器和单位转换 Agent；当前未保留传入 config。 |
| [08 Streamlit Template](../../resources/agents/08-langchain-streamlit-template/bindings/bridge.py) | 提取原生工厂而不启动 UI；需复核私有 thread 配置。 |
| [09 Curiosity](../../resources/agents/09-curiosity/bindings/bridge.py) | SQLite 路径和原生 thread；需复核私有 thread 配置。 |
| [10 Readwren](../../resources/agents/10-readwren/bindings/bridge.py) | 先启动访谈再传输入；公开方法没有 config 参数。 |
| [11 TableGPT](../../resources/agents/11-tablegpt-agent/bindings/bridge.py) | Sandbox、日期与 parent ID；当前文字输入未转换附件。 |
| [33 Open Notebook](../../resources/agents/33-open-notebook/bindings/bridge.py) | 异步服务和会话初始化，及拥有的进程清理。 |
| [34 AI Data Science Team](../../resources/agents/34-ai-data-science-team/bindings/bridge.py) | 固定 CSV、公开 `invoke_agent` 和结果读取。 |
| [35 Local Deep Research](../../resources/agents/35-local-deep-research/bindings/ldr_bridge.py) | Settings snapshot 和原生 API 的主线程限制。 |
| [37 Article Explainer](../../resources/agents/37-article-explainer/bindings/bridge.py) | 严格的当前消息输入；实际已启用 checkpoint，文字说明仍有相反描述。 |
| [38 GPT Researcher](../../resources/agents/38-gpt-researcher/bindings/gpt_researcher_bridge.py) | 包含 `publish_formats` 的完整 task 和异步研究图。 |
| [39 TradingAgents](../../resources/agents/39-tradingagents/bindings/tradingagents_bridge.py) | 显式 ticker/日期解析与公开生命周期外的配置上下文。 |
| [48 EvoScientist](../../resources/agents/48-evoscientist/bindings/bridge.py) | Workspace 准备和明确的无人值守部署配置。 |

## 审核和验证

模块说明中写明真实入口、具体输入示例、config/context 处理、返回字段、原生异常、会话行为和资源所有权。`requirement.md` 应与部署接口一致：上游 UI 支持上传文件，不代表文字 binding 也支持。固定数据、关闭人工交互或限制研究预算等部署选择需要明确说明，缺失的选择通过 onboarding answers 补充。

在仓库根目录、已配置 ABB 环境和 KUMA 校验依赖的情况下，替换单元路径后执行下面的离线检查：

```python
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin

print(validate_unit(Path("resources/agents/NN-name"), plugin))
```

静态检查覆盖配置、binding 语法和工厂、可识别的部分输入不匹配、Docker 声明和 SDK Profile。它不能证明原生 import 成功、每条分支保留 config、资源正确清理，或模型和工具工作流完成。没有传入 SDK catalog context 时，这次调用不会核对实时策略目录。

真实接入检查需要在 registry 中启用 Agent，然后使用已经核对过的 CLI 命令：

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

Local SDK 使用通用文字 Case 和本地 Judge；KUMA 使用配置的服务。两者都可能调用付费目标模型，通用 Case 也可能不适合严格的原生问题格式，因此应另保留代表性的有效输入用于 binding 调用检查。核对 config 转发时保留实际输入、输出和 traces。对话型应用应检查同一个 Case 的两次输入和不同 Case 的隔离；无状态应用则检查其行为仍然无状态。依据实际资源检查原生失败传播和自身资源清理。

分别报告静态校验、真实执行和 Judge 发现。认证与结果查看流程见[添加指南](How%20To%20Add%20Agent.zh-CN.md)。

## 实现依据

- [Adapter 配置](../../agentbench/adapter/langgraph/config.py)、[loader](../../agentbench/adapter/langgraph/loader.py) 和[调用实现](../../agentbench/adapter/langgraph/adapter.py)。
- [Worker 调用](../../agentbench/runtime/agentcontainer/worker.py)和 [Case 资源所有权](../../agentbench/runtime/agentcontainer/session.py)。
- [Binding 生成要求](../../agentbench/onboarding/build_agent_env/frameworks/langgraph/assets/bindings/prompt.md)和[静态校验](../../agentbench/onboarding/build_agent_env/frameworks/langgraph/binding_validation.py)。
- [KUMA onboarding 要求](../../agentbench/sdk/plugin/kuma/onboarding.py)和 [Docker binding 布局校验](../../agentbench/onboarding/build_agent_env/build_dockerfile/binding_layout.py)。
