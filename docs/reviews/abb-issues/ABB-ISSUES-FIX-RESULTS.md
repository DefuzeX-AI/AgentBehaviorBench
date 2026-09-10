# ABB 十项修复实施与验收记录

日期：2026-09-10。范围：[原始报告](ABB-ISSUES-REPORT.md) #1–#10；设计依据：[修复计划](ABB-ISSUES-FIX-PLAN.md)。

十项代码修复已落地，保持 CLI → SuiteRunner/EvaluationRunner → Runtime/Adapter 的分层。
本轮未修改 Company Agent 的上游 `agent/` 源码、业务提示词或搜索实现。
既有 `agentbench/cli/main.py` 修改和 Deer Flow 删除均保留。本记录最初生成于提交前；Git 提交记录记录后续交付状态。

## 逐项交付

以下路径均相对 `AgentBehaviorBench/`。

| Bug | 修复与代码位置 | 验收依据 | 避免硬编码与架构边界 |
| --- | --- | --- | --- |
| #1 | `runtime/docker/runtime.py`、interceptor `entrypoint.py`：CA 留在容器 tmpfs；只导出公有 PEM，经 TLS 校验后由宿主原子写入 | `tests/observe/test_ca_lifecycle.py`：真实启动、宿主文件所有权、无私钥/可写 CA mount、失败清理；真实 interceptor 协议测试 | 不使用 chmod 777、固定 UID、DAC_OVERRIDE 或 privileged；保留既有隔离策略 |
| #2 | `harness/runner/benchmark_runner.py`、`running_agent.py`：一次 Run 使用一个循环，所有 Input await ainvoke，循环关闭前 aclose | 三 Input 同循环、活跃循环要求 arun、Host 失败/取消、真实 Docker worker | 同步 API 仅包装异步入口；SDK handshake 仍由原 Runner 驱动 |
| #3 | `observe/correlation.py`：httpx/httpx2/requests/aiohttp scoped hooks；`interactions.py` 统计缺失关联并提示 | 真实 loopback 请求、redirect 到非目标 host、不泄露复用请求、并发隔离、实际 OpenAI/Tavily 客户端、interceptor 剥离 header | 按传输类型注册，host 来自 manifest；只用记录的 span ID 建立因果关系，不按时间猜测 |
| #4 | `adapter/langgraph/config.py`、`adapter.py`：可选 JSON 兼容 context，独立 keyword，每次 deep copy | 真实 LangGraph dataclass/Pydantic Runtime，sync/async；同步 fallback 深复制 | 不认识 Agent 的 context 字段；保留 None 与空映射区别，由 LangGraph 负责 schema 转换 |
| #5 | CLI `features/run.py`、`certify.py`：增加 --registry 并传到既有入口 | 外部临时工作区、另一 cwd、真实 CLI certify→run；外部变 ready，内置 Registry 字节不变 | 共用现有路径解析、原子状态更新；没有另一套 Registry 实现 |
| #6 | `features/evaluate.py`：复用 SuiteRunner 和 run_benchmark_once；增加 --result-output；保留 --output 的 SDK 含义 | 不写私有产物的 SDK；1 Case 3 Inputs；pass/issue 都保存；标准事件脱敏且不修改业务输入 | CLI 不解析 KUMA 私有文件、不重写 SDK handshake；通用结果由 ABB 保存 |
| #7 | 新 `observe/invocation.py`、`host.py`；worker 复用；`otel/routing.py` 限制共享 provider 处理器数量 | 真实 Host framework/OTel、公共 Judge、失败/取消保留、独立 Input、共享 provider 不关闭；Docker 多 invocation 回归 | Host 明确 network/sdk_wire unavailable；没有假造网络 trace 或重放 JSONL 生成假 span |
| #8 | `cli/viewer.py`、view/presentation、前端：缺资产在监听前失败，自动 viewer 失败不影响结果 | 缺 index/引用 JS 的回归、真实 HTTP Viewer 测试、19 项前端测试及生产构建 | 复用同一预检；构建是显式步骤，预构建资产运行时不依赖 Node |
| #9 | `resources/registry.toml`、Layout、外层 requirement 文档、Registry fixture 测试 | 核查现有产物没有保留完整 certify 记录；Company 暂回 adapting；现有认证语义测试通过 | ready 仍表示执行接入，不表示 Judge pass；没有把特定 Agent 名称或数量写入通用规则 |
| #10 | `runtime/agentcontainer/config.py` 导出纯结构校验，Registry 复用 | in_process 无 Dockerfile 可加载；Docker context 相对路径、自定义文件、越界与 argv 校验 | 不读密钥、不连 Docker；Dockerfile 相对 build.context，runtime 缺省仍为 in_process |

## 已执行验证

- Python 全套：`306 passed, 10 skipped`（在允许绑定本机端口的环境运行）。
- Docker 显式启用的 CA 成功/失败清理 + interceptor 协议测试：`3 passed`。
- Docker worker 多次调用/异步执行/只读隔离：`1 passed`。
- 前端：`npm test`，`19 passed`；`npm run build` 成功。Vite 仍提示既有主 bundle 较大，不影响构建。
- `compileall` 成功；本轮变更的 whitespace 检查通过。既有 main.py 空白问题未混入修复。
- `git diff -- resources/agents/01-company-research-agent/agent` 为空。

回归入口：`tests/test_issue_contracts.py`、`tests/observe/test_issue_regressions.py`、
`tests/observe/test_ca_lifecycle.py`，以及原有 Registry/SDK/Viewer/worker/OTel 测试。
测试中的假服务与 fixture 仅用于离线验证，没有替换生产 Agent 的模型或搜索调用。

## 验证边界

1. 本机是 macOS + Docker Desktop，尚未取得报告中的原生 Linux Docker 主机。
   #1 消除了宿主 UID 写入依赖，但不能将 Desktop 测试写成原生 Linux 已通过。
   在原生 Linux 可直接运行：
   `ABB_DOCKER_TEST=1 .venv/bin/python -m pytest -q tests/observe/test_ca_lifecycle.py`。
2. 真实客户端验证针对本机已安装版本：httpx 0.28.1、httpx2 2.12.0、aiohttp 3.14.3、OpenAI 2.54.0。
   没有将报告中的其他 OpenAI 版本推定为已验证。所有调用均发往本机假服务。
3. 本轮没有运行真实付费模型/Tavily 研究或完整 KUMA certification；Company 保持 adapting。
   历史 Judge 的格式/公司身份问题属于 Agent 与任务接口能力，不由这十项基础设施修复自动消除。
4. Browser 工具访问本机 Viewer 被客户端阻止（ERR_BLOCKED_BY_CLIENT），未声称完成视觉验收。
   HTTP Viewer、产物 API、前端单测和构建已验证；本次启动的临时 Viewer 已关闭。
5. 默认 pytest 的 10 项 skip 是 opt-in 测试；本轮另行运行了上列 4 项 Docker 检查，未把所有 skip 算作通过。

## 使用方式

```bash
# 外部 Registry 完成认证后参与批量评测
python -m agentbench certify my-agent --registry /path/to/workspace/resources/registry.toml
python -m agentbench run --registry /path/to/workspace/resources/registry.toml --no-view

# SDK 私有输出与 ABB 标准结果分开指定
python -m agentbench evaluate my-agent --registry /path/to/workspace/resources/registry.toml \
  --sdk python:my_sdk --sdk-options options.json --result-output results/evaluation.json

# 使用终端实际打印的带时间戳结果文件
python -m agentbench view results/evaluation-YYYYMMDD-HHMMSS.json
```

初次展示前在 `AgentBehaviorBench/web` 执行 `npm ci`、`npm run build`。
本轮具体接口说明已同步到 `docs/CLI.md`、`docs/Agents/Runtime.md` 和 `docs/observe/architecture.md`。
