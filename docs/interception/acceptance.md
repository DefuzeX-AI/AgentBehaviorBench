# 模型拦截实现与验收记录

## 结论（2026-09-09）

已经实现并实测一条共用的执行链：原 Agent 客户端 → Docker 网络拦截 →
按源协议转换 → 可配置 OpenRouter 目标 → 按源协议回传 → 原客户端解析。
没有将 Gemini 强制改为 REST，没有在 Agent 中替换 Google 客户端。

这是一份**有边界的兼容矩阵**，不是“市面所有模型、所有 SDK、所有参数均已兼容”的声明。
模型名称不等于传输协议，配置和 smoke 记录也不等于真实网络证据。
wangyi 的统计依据与限制见 [inventory](../reviews/wangyi-llm-inventory.md)。

## 文件职责

| 位置 | 职责 |
| --- | --- |
| agentbench/runtime/interception/ | 读取 Agent 声明、目标模型配置、临时凭据、CA 信任 |
| agentbench/runtime/docker/ | 现有镜像构建、网络命名空间、容器生命周期与清理 |
| services/model-interceptor/.../policy.py | 模型路由、工具白名单和拒绝规则 |
| services/model-interceptor/.../auth.py | 临时凭据校验与替换；Google header/query key |
| services/model-interceptor/.../targets.py | 目标端点与模型；不写 Company 或 DeepSeek 特判 |
| services/model-interceptor/.../wire/ | 每请求独立协议 Strategy；JSON/SSE、protobuf/gRPC、NDJSON |
| services/model-interceptor/.../protocols.py | trace 解码插件，不负责完整双向转换 |
| agentbench/observe/ | 框架回调、完整事件保存、状态汇总与终端查看 |
| resources/agents/01-company-research-agent/bindings/ | Company 生命周期和 Tavily 结果语义 |
| tests/fixtures/llm-probe/ | 可选择客户端、源模型和调用方式的专用测试 Agent |
| tests/acceptance/interception/ | 受控 TLS 上游、故障场景、Docker 与真实调用验收 |
| tests/interception/ | 协议与代理生命周期离线回归 |

新增协议通过 `defuzex.model_interceptor.wires` 工厂注册，返回每次调用独立的
decode/response/stream Strategy；已有 auth、target、trace decoder 插件保留。
新增 Agent 先统计真实的 host/path/protocol/credential，再声明路由，不靠模型名称猜 SDK。
测试 Agent 未加入生产 enabled Registry，防止普通运行意外触发几十次计费请求。

## 已实测的调用矩阵

每项使用原客户端，不 monkey-patch SDK 传输，不设置 OpenRouter 为客户端 base URL。
真实调用统一把目标选为 `openai/gpt-4.1-mini`，源模型分别保留原供应商名称。

| 客户端 / API | 方式 | 受控 Docker | 真实 OpenRouter |
| --- | --- | --- | --- |
| OpenAI Chat Completions | sync/async × unary/stream | 4/4 | 4/4 |
| OpenAI Responses | sync/async × unary/stream | 4/4 | 4/4 |
| Google GAPIC gRPC v1beta | sync/async × unary/stream | 4/4 | 4/4 |
| Google GAPIC REST | sync × unary/stream | 2/2 | 2/2 |
| LangChain Google（原生 grpc_asyncio） | ainvoke/astream | 2/2 | 2/2 |
| Anthropic Messages | sync/async × unary/stream | 4/4 | 4/4 |
| Ollama chat/generate（localhost:11434） | sync/async × unary/stream | 8/8 | 8/8 |
| 原始 HTTP：DeepSeek、DashScope 兼容端点 | unary/stream | 4/4 | 4/4 |
| 合计 | | **32/32** | **32/32** |

主要固定版本：mitmproxy 12.2.3、Google Generative Language 0.12.0、
LangChain Google 3.0.3、OpenAI 2.54.0、Anthropic 0.125.0、Ollama 0.6.2。
其他依赖仍按版本范围解析，不能把本次结果外推到所有历史/未来 SDK 版本。

受控测试把 SSE 切成 7 字节块（另有单字节离线测试），包含中文、U+2028/U+2029、
多个事件、usage 和结束标记；刻意延迟后续事件，并断言首段文本早于完成至少 100ms。
真实调用返回“测试 OK”；32 个 request ID 与 32 个 response ID 完全对应，
上游主机均为 openrouter.ai，含 6 次原生 gRPC 请求，0 次 llm_error、0 次 truncated。
已扫描该真实验收目录，没有发现 .env 中的真实凭据内容。

证据：

- 受控矩阵与 13 项额外检查：
  [controlled.json](../../results/interception/f27d086fe7ab4ab5aea94a5b2bc655d8/controlled.json)
- 同次完整代理 trace：
  [controlled.trace.jsonl](../../results/interception/f27d086fe7ab4ab5aea94a5b2bc655d8/controlled.trace.jsonl)
- 真实 32 项矩阵：
  [live.json](../../results/interception/f4708525b23b499b833209a1dc145962/live.json)
- 同次真实网络 trace：
  [interceptor.jsonl](../../results/interception/f4708525b23b499b833209a1dc145962/interceptor.jsonl)
- 最小真实调用也独立保留在 results/interception/50173df8946f4fcf9e17a542991129f1。
- 调试过程中失败的目录保留；不可拿它们当成最终通过结果。

## 额外检查

13/13 通过：gRPC 错误 token、不支持 tools、上游 429、流中错误、缺结束标记、
deadline、主动 cancel、并发、gzip；未声明路径、未声明端口、UDP 和 IPv6 阻断。
这些是受控场景，不向真实模型发送故障标记。

代理镜像离线单测 40/40 通过，包括：插件异常时凭据不会泄漏到源供应商；
HTTP/1 空中间分片不产生结束块；gRPC 流失败后仍保留非零 trailers；
Unicode、参数拒绝、gzip、未知 protobuf 字段和工具路由边界。

本地全量 pytest：192 passed、7 skipped、3 failed。
3 项失败均为既有 examples.local_sdk 缺失（tests/test_sdk_injection.py），
没有用删测试或虚假 SDK 替代。需要临时监听端口的 viewer 测试在允许本机监听后通过。
普通 pytest 不调用真实模型，Docker/真实调用通过显式 acceptance 命令运行。

## Company 完整真实执行

通过 observe CLI 对 Microsoft 执行了一次原生 Company 研究（600 秒上限）。
10/10 模型调用均到 OpenRouter 且 request/response ID 对账成功：
gpt-5.1 源调用 4 次、Gemini 原生 gRPC 4 次、gpt-4o 源调用 2 次。
实际目标仍为 openai/gpt-4.1-mini，没有直连源模型执行。
最终报告 13,881 字节；132 个框架 span 均结束，0 个 llm_error。

最终状态为 **degraded，而非 succeeded**：80 次真实 Tavily 调用中，
4 次 extract 返回 failed_results 且没有成功结果。Agent 完成报告并不意味着
搜索全部成功；新的 tool_outcome 检查准确识别了这个区别。
本轮未使用固定资料替换搜索，也未以报告非空证明研究质量。

- [运行结果](../../results/interception/company/f9931868a6d143d0af33b48133973e57/run.json)
- [报告](../../results/interception/company/f9931868a6d143d0af33b48133973e57/report.md)
- [网络 trace](../../results/interception/company/f9931868a6d143d0af33b48133973e57/network.jsonl)

测试容器和临时网络已清理；证据文件和可复用镜像保留。

## 同时修复的观察问题

- 删除 observe/google_rest.py 及 Company 的调用点；Google CA 通过标准环境变量信任。
- JSONL 与 SSE 不使用 Unicode-aware splitlines 切记录，避免完整 trace 被误报损坏。
- Ollama NDJSON 使用 Unicode 转义，原客户端恢复原文本，不把 Unicode 行分隔符当记录边界。
- Tavily 仍执行真实 search/extract/crawl；binding 检查 failed_results，通用 observer 记录
  tool_outcome，不改变返回值。部分失败可把 observe 状态标为 degraded，报告仍保留。
- gRPC 成功必须正确回传 grpc-status；HTTP 200 本身不算成功。
- 认证和路由先在请求副本上完成，插件异常会阻断，不把真实目标 Key 带到原始域名。

## 当前边界：尚未验收或明确不支持

- Gemini/Ollama 的跨协议桥目前是文本子集。tools/function calls、多模态、
  Google safety/cached content、JSON schema/部分特有采样参数等没有完成映射，明确拒绝。
- OpenAI/Anthropic 原生 JSON 参数保持其格式，但本次只实测文本；不能据此宣称所有工具、
  图像、音频、结构化输出均通过。还需按目标模型能力补专项矩阵。
- OpenAI legacy Completions/Embeddings 有协议端点策略，但未完成原客户端/真实调用验收。
- 新 google-genai SDK、Node/Java/Go 等其他语言版本、Azure/Vertex/Bedrock 签名协议、
  WebSocket Realtime、gRPC-web、双向流、HTTP/3/QUIC、本地进程内推理未验收。
- IPv6、非 DNS UDP 是阻断而非协议支持。工具 egress 必须显式声明；
  这是一项兼容性变更，原先依赖任意外网访问的 Agent 需要补清单。
- CA 必须被客户端接受；证书 pinning、客户端证书认证和不接受临时凭据的客户端需要另行设计。
- gRPC 目前有 run/call ID，不声称已精确关联 LangChain span；未实现完整 OTel/LangSmith 集成。
- trace spool 并不代表无限容量；最终序列化受容器内存与临时存储上限约束。
- 研究报告非空只能证明执行交付，不能证明信息事实和研究质量正确。

## 如何继续扩展

先加失败的原客户端受控网络用例，再实现独立 Wire Strategy 或扩展既有语义映射；
补错误、流式、取消和旧协议回归；最后才跑显式真实验收。对于不支持的协议保持拒绝，
不能降级成绕过拦截或替换 Agent 原客户端。

```sh
python -m tests.acceptance.interception.run --list
python -m tests.acceptance.interception.run --controlled --faults
python -m tests.acceptance.interception.run --live --model openai/gpt-4.1-mini
python -m tests.acceptance.interception.run --live --cases google.grpc.async.stream --model openai/gpt-4.1-mini
```

--source-model 可指定来源（例如 google=gemini-2.5-flash）；--model 才是
OpenRouter 实际执行目标。真实模式会计费，默认测试不会自动调用真实模型。
