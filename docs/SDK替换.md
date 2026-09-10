# 替换评测 SDK 与 Case 来源

KUMA 是一个评测 SDK：提供 Case、接收 Agent 输出、返回 Judge 结果。
被测 Agent 是另一个角色，由 Registry 与 Agent adapter 接入。
本页讲的是替换评测 SDK 或它的 Case 来源。

## 1. 接口放在哪里

公开接口统一在 `agentbench/sdk/contracts.py`，从 `agentbench.sdk` 导入。
采用 Adapter 模式，把第三方的数据结构和方法转换为 ABB 认识的接口。
CLI 与 SuiteRunner 通过同一个 factory 选择实现，形成可替换的 Strategy。

| 接口 | 需要提供的行为 |
| --- | --- |
| `SDK.create_run(repo_path=..., **options)` | 创建一个新的 Case 执行会话；每个 Case 都调用一次。 |
| `Run.get_input(full=True)` | 返回带有 `input_id`、`payload` 的 Input；全部结束返回 `None`。 |
| `Run.submit(output)` | 接收本次输出，推进到下一个 Input；最后可返回 Report。 |
| `Run.submit(status="failed", error="...")` | 记录 Agent 执行失败。 |
| `Run.run_id / state / history / report` | 提供会话标识、状态、提交记录、最终报告；history 内部结构由 SDK 自己决定。 |
| `Report` | 提供 `status`、`confidence`、`issues`、`evidence_gaps`；`status="pass"` 表示通过。 |

同一个 Input 提交前保持 pending；提交后才能推进。字段名或 API 不同的 SDK
需要写一层 adapter，无需修改 CLI、SuiteRunner 或被测 Agent。

## 2. 先用 JSON Case 替换

仓库提供 `examples/case_file_sdk.py`，它读取一个 JSON Case，并用输出完全相等
作为 Judge 规则。它不导入 KUMA，不需要评测服务凭证。
示例 Case 在 `examples/echo_case.json`，包含两个 Input：

```json
{
  "inputs": [
    {"input_id": "one", "payload": "你好", "expected_output": "你好"},
    {"input_id": "two", "payload": "ABB", "expected_output": "ABB"}
  ]
}
```

这里的 Case 适合 echo Agent。接入自己的 Agent 时，按它接受的输入格式编写
`payload` 与期望输出；能正常执行与 Judge 判定通过是两件事。
示例是最小演示，复杂判分规则应在自己的 evaluator 中实现。

## 3. Python：直接传入 SDK

```python
from examples import case_file_sdk
from agentbench.harness import SuiteRunner, load_registry

registry = load_registry("resources/registry.toml")
agent = registry.find("你的已注册AgentID", enabled_only=False)
result = SuiteRunner(
    sdk=case_file_sdk,
    sdk_options={"case_file": "examples/echo_case.json"},
).run([agent])
print(result.passed)
```

替换时修改 `sdk=` 与该 SDK 所需的配置。SuiteRunner 仍按 Registry 的 Case
数量创建新会话、执行 Agent、汇总结果。

## 4. CLI：传入 SDK 引用

在仓库根目录、已经激活的虚拟环境中执行：

```bash
python -m agentbench evaluate 你的已启用AgentID \
  --sdk python:examples.case_file_sdk \
  --sdk-options examples/case_file_options.json
```

| 参数 | 含义 |
| --- | --- |
| `evaluate` | 对一个 Agent 执行一个 Case；不修改 Registry 状态。 |
| Agent ID | Registry 中已经 enabled 的目标 Agent。 |
| `--sdk python:examples.case_file_sdk` | 导入这个模块，使用它的 `create_run`。 |
| `--sdk-options` | 读取 JSON 配置；示例内容为 `{"case_file":"examples/echo_case.json"}`。 |

相对路径以当前工作目录为起点。批量运行使用 `run --sdk ...`；验证 Agent
接入使用 `certify AgentID --sdk ...`，其原有选择和状态更新规则仍生效。

第三方发布 PyPI 包时，可以声明 entry point：

```toml
[project.entry-points."defuzex_agentbench.evaluation_sdks"]
my-evaluator = "my_package:sdk"
```

安装后便可使用 `--sdk my-evaluator`。PyPI 负责安装，CLI 的 `--sdk` 负责选择。

## 5. 当前边界

- KUMA 的导入、密钥、镜像构建、worker、提交记录和证据解析集中在
  `agentbench/sdk/`。`evaluation/` 下旧路径保留兼容转发。
- 省略 `--sdk` 时，CLI 与 SuiteRunner 仍默认选择 KUMA；显式选择其他 SDK
  不会注入 KUMA 的源码路径、密钥参数、输出目录或超时默认值。
- 简单 `create_run` SDK 在宿主 Python 进程中执行；Agent 使用自己声明的 runtime。
- 若评测 SDK 必须和 Agent 一起部署进容器，它需要实现 `EvaluationSDKPlugin`，
  返回自己的 `EvaluationRunner`。目前还不支持把任意 Python 对象自动装进容器，
  或让任意 SDK 自动产生 KUMA 同款证据与网页 artifacts。

更完整的部署接口见 [架构说明](architecture/evaluation-sdk-plugins.md)。
