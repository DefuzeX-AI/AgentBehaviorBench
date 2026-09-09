# Observe：从 Company 开始测试

Observe 不创建评测 Case、不调用 Judge，也不需要 DefuzeX SDK。
当前执行链为 Registry → RuntimeFactory → ContainerAgentAdapter（oneshot）→
DockerRuntime / DockerSession → worker → AdapterFactory → LangGraphAdapter → Company 原生 Graph。

## 启动

在 AgentBehaviorBench 目录执行：

```sh
source .venv/bin/activate
python -m agentbench observe --list
python -m agentbench observe
```

第二条显示所有 `enabled = true` 的 Agent，包括 adapting，不会修改 Registry 状态。
第三条显示相同菜单，输入 `1` 选择 Company，再输入公司名称、网址、总部和行业。
输入 `q` 退出；无效编号可以重试。

已知道编号时，直接执行，不再显示选择菜单或重复询问编号：

```sh
python -m agentbench observe 1
```

选中后仍需输入公司研究信息。模型默认读取 `.env` 的 `OPENROUTER_MODEL`；
`--model` 仅用于覆盖模型名称，不能用 `--model 1` 选择 Agent。

首次安装：`python3 -m venv .venv`，激活后 `python -m pip install -e .`。
宿主机不需要安装 Company 的原客户端依赖；真实执行使用 Docker 镜像。
Docker Desktop 必须运行。

本机 Python 3.14 的 editable 安装 `.pth` 文件会被环境标记为 hidden，Python 因而跳过它。
所以这里使用仓库目录内的模块入口，不依赖 `agentbench` console script 的 editable 注册。

## 凭据

参考 [environment.example](environment.example)，在项目根目录的 `.env` 中填写
`OPENROUTER_API_KEY`、`OPENROUTER_MODEL`、`TAVILY_API_KEY`。也可使用 `--env-file PATH`。
不要提交真实 Key。已有终端环境变量优先于 dotenv。

OpenRouter Key 只交给 Interceptor；Company 得到本次容器的临时 OpenAI/Gemini token。
Tavily 接收真实搜索 Key。生产执行不会注入离线资料。
真实研究会消耗模型和搜索额度；测试不会自动执行真实收费调用。

## 不交互执行

```sh
python -m agentbench observe 1 --input examples/observe/company.json --timeout 1800
```

编号位置也接受稳定 ID `company-research-agent`。保留 `--agent` 兼容旧命令，
但不能和位置参数同时使用。`--timeout` 只限制一次容器执行，
不包含镜像构建时间。一次输入创建一个新容器，不保留多轮内存。

## 查看输出

每次运行创建 `results/observe/<run-id>/`：

- `run.json`：运行状态、输入、输出和 trace 计数。
- `report.md`：成功时保存 Company 报告。
- `network.jsonl`：Interceptor 的原始请求/响应证据。
- `invocation-*/input/request.json`：只读挂载的调用输入。
- `invocation-*/output/result.json`：带调用身份的 worker 结果。
- `invocation-*/output/framework.jsonl`：节点、模型和 Tavily 方法的回调记录。
- `invocation-*/diagnostics.json`：退出码和末尾 stdout/stderr。

```sh
python -m agentbench observe --show results/observe/实际运行ID
```

终端查看器显示框架 span 层级、完成/失败/未结束状态，以及网络请求和框架 span 的关联。
两类证据不合并成重复的 LLM span。无法关联的请求明确显示 `uncorrelated`。
文件可能包含研究内容和个人数据；trace 做凭据脱敏，但不是任意敏感内容的自动审查器。

退出码：成功或 `q` 为 0，运行/配置错误为 1，参数解析错误为 2，Ctrl+C/EOF 为 130。
报告返回但观察到失败操作时，run.json 标记 `degraded` 并退出 1，报告和证据仍保留。

## 支持边界

当前 observe 支持 Docker oneshot 执行。服务型 caller 保持兼容，但尚未有 observe 服务调用策略。
LangGraph 回调观察器和网络 Interceptor 已接入；未宣称实现完整 OTel Collector 或 LangSmith 导入。
Gemini 桥支持文本、普通响应、流式响应和常用生成参数；图像、原生工具、缓存、
自定义安全策略及其他未支持参数明确拒绝，不静默删参数。
Company 已配置专用生命周期绑定，原始 `agent/` 源码不改动。

详见 [架构](architecture.md) 和 [验收记录](validation.md)。
