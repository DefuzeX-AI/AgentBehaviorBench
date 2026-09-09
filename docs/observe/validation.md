# Observe 验收记录（2026-09-09）

## 本轮结果

| 检查 | 实际结果 |
| --- | --- |
| `agentbench observe --list` | 展示 1 号 enabled/adapting Company，不要求 SDK 或 Key |
| 独立子进程 | 实际异步 StateGraph 两节点运算、中文/引号/换行、回调父子关系通过 |
| CLI 全链路 | 输入编号 1 → 实际 Docker → 运算结果 → JSONL → 终端查看通过 |
| Docker 隔离 | 两次独立调用、不同 invocation ID、非 root、输入/源码不可写、结果可写通过 |
| Company 原生 Graph | 保持源码不变，原模型客户端及 Tavily 方法读取受控 HTTP 响应，完整 Graph 返回报告 |
| Company 实际镜像 | Python 3.11 镜像真实构建；断网容器内完整原图运行通过，无评测 SDK |
| Gemini 原客户端 | 固定 `langchain-google-genai==3.0.3` 的 ainvoke/astream 实际解析转换后的响应通过 |
| Gemini 流式转换 | 1/2/3/11 字节等任意分片、UTF-8、CRLF、多事件、结束标记、usage、缺结束标记拒绝通过 |
| Interceptor 实际镜像 | 真实 mitmproxy Request/Response 对象验证认证替换、普通/流式回译、429 与原 OpenAI 流式回归通过 |
| 失败和清理 | 非零退出、缺文件、损坏文件、缺字段、旧调用 ID、超时、异步取消均有测试 |
| 构建安全 | 排除 dotenv/venv，拒绝复制后的源码符号链接及 bindings 越界 |
| 静态检查 | compileall、git diff --check 通过 |

完整 observe 验收命令：

```sh
ABB_DOCKER_TEST=1 .venv/bin/python -m pytest tests/observe -q
```

最终结果：**37 passed**。这是离线验收，包含真实 Docker，并非全部使用 mock。
真实镜像测试中的上游响应是受控资料，不能用作真实研究质量证据。
测试完成后检查 `docker ps --filter name=defuzex-`，没有残留运行容器。
构建出的镜像保留供后续测试复用，Docker Desktop 已启动。

## 全项目回归

`.venv/bin/python -m pytest -q`：**146 passed, 3 failed, 6 skipped**。
6 个跳过包含 4 个显式 opt-in Docker 测试（已在上面的专门验收中执行）和 2 个原有跳过。

3 个已有失败都在 `tests/test_sdk_injection.py`：

- `test_offline_example_sdk_executes_real_langgraph`
- `test_cli_python_entry_passes_sdk_to_real_execution`
- `test_cli_module_selection_and_options_reach_run`

原因是当前仓库缺少这些测试导入的 `examples/local_sdk.py`。
首次回归已复现；没有为让测试变绿而跳过、替换或修改这三个测试。
首次沙箱回归另有本机 HTTP 端口权限失败，在授权的完整回归中已通过。

另外发现本机 editable 安装产生的 `.pth` 带 macOS hidden 标记，
Python 3.14 因而跳过它，导致 console script 找不到包。手动移除标记后会被环境重新加上。
这是尚存的安装环境限制：交付统一使用仓库目录内 `python -m agentbench observe`，
并增加模块 CLI 入口的独立子进程回归测试；不宣称已修复本机 console script。

## 尚未验收

本机未配置 `OPENROUTER_API_KEY`、`OPENROUTER_MODEL` 和 `TAVILY_API_KEY`。
因此没有执行以下收费/真实联网检查：

1. 原模型客户端经实际透明网络/CA → Interceptor → OpenRouter 的最小真实调用。
2. Tavily 真实 search/extract/crawl。
3. 一次真实 Company 研究，核对完整 trace、模型未绕过路由及报告内容。

现有离线镜像测试验证了组件与原客户端的协议处理，**不等于透明网络拦截的端到端实测**。
填好凭据后按 README 启动，将 run.json、network.jsonl 和 framework.jsonl 一起检查。
报告非空只证明输出存在；不代表研究质量达标。

完整 OTel Collector、LangSmith 数据导入、服务型 observe caller 和多轮内存会话不在本版已实现范围。
