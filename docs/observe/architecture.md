# Observe 模块边界与 Agent 接入

| 层 | 位置 | 职责 |
| --- | --- | --- |
| CLI | `agentbench/cli/features/observe.py` | enabled 菜单、原生输入、参数与退出码 |
| 编排 | `agentbench/observe/service.py` | 不依赖评测 SDK 的单次运行 |
| 执行策略 | `runtime/agentcontainer/invocation.py` | 独立输入/结果、超时、结果身份与退出码校验 |
| Docker | `runtime/docker/` | 复用镜像、隔离、网络、进程清理 |
| 容器入口 | `runtime/agentcontainer/worker.py` | 直接选择 Adapter，不再次选择 Runtime |
| 框架适配 | `adapter/langgraph/` | 加载、异步调用、config 和输出提取 |
| 特殊绑定 | Agent 外层 `bindings/` | 原生构造输入、生命周期和明确结果位置 |
| 观察器 | `observe/observers.py`、`langchain.py`、`tools.py` | 可独立注册的观察策略 |
| 传输兼容 | `observe/google_rest.py` | 固定版本 Google SDK 的异步 REST 调度 |
| 网络协议 | 独立服务 `defuzex_model_interceptor/gemini.py` | 双向转换与增量流解码 |
| 持久化/查看 | `observe/store.py`、`review.py` | JSONL 证据、运行摘要与终端层级 |

## 接入另一个 LangGraph Agent

1. 保留外层 unit / 内层 agent 源码布局。Registry 登记真实框架，enabled 与 ready 分开。
2. 普通 graph 继续使用原 `langgraph.json` 的 `file.py:attribute`，支持编译图和无参工厂。
3. 必须构造原生输入或管理特殊生命周期时，新增外层 `bindings/<name>.py`，
   manifest 配置 `adapter.binding = "<name>.py:<factory>"`。绑定不能越出 bindings 目录。
4. 绑定提供 invoke/ainvoke；返回真实结果，配置 output_key；不能用日志或中间结果冒充最终输出。
5. Docker oneshot 声明 `runtime.execution = "oneshot"`，launch 指向共用 worker。
   镜像 COPY `.abb-runtime/` 到 `/opt/abb-runtime/`，配置 PYTHONPATH，并保留 `/opt/agent/agent.toml`、
   `/opt/agent/agent/` 和可选 bindings。构建器自动注入当前执行包，不安装评测 SDK。
6. observe.input_fields 声明交互文本字段；未声明时 CLI 接受原生 JSON。
7. 声明真实模型路由与临时凭据，声明必须的外部工具 Key。未知协议不可冒充兼容。
8. 先离线图/子进程，再真实 Docker、原客户端受控上游，再由用户提供凭据做真实测试。

新框架增加 AdapterFactory 注册，新观察方式增加 ObserverFactory 注册；两者不绑定 Docker 实现。
本版内置 LangGraph callbacks，不把它冒充 OTel 或 LangSmith。

## 安全和归属

每次调用有独立目录与 JSON 输入；没有把用户输入拼入 shell。
输入、源码和根文件系统只读，只有当前结果挂载可写。镜像必须非 root。
worker 结果必须有正确 schema、Agent ID、run ID 和成功退出码。
取消/超时终止当前容器并保留诊断，不复用上一次结果。异步取消在后台线程结束清理后返回。
当前结果 JSON 上限 32 MiB；JSONL 保存完整回调内容，长研究可能产生较大文件。

网络与框架以本次 run ID 归组，模型请求通过限于声明模型域名的临时 header 携带 framework span ID。
Interceptor 消费并移除此 header，外部模型不会收到它。关联只是观测证据，不是权限凭据。

Company 的 Google SDK 3.0.3 会将普通 async REST 配置切回 grpc_asyncio。
独立桥调度原同步 REST SDK 到线程，并保留原 LangChain 异步解析路径。
不能把“增加一个 decoder”视为 Gemini 协议兼容；请求、响应、错误、SSE/JSON-array 都有转换。
