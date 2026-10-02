# Ground truth 与发现结果评估

[使用指南](Guide.zh-CN.md) · [English](../Ground%20Truth.md)

Ground truth 保存真实 Agent 的已确认缺陷：人工检查原始观察，并用同一 Case 多轮执行确认。Benchmark Overview 展示生成的 Case 是否复现这些缺陷，以及 Judge 是否正确指出它们。目前实现的是宿主侧的参考数据和评估接口，尚无自动质量评估器或缺陷匹配器。

## 保存已确认缺陷

固定目录位于 `agent.toml` 旁，不放入上游 `agent/` 源码：

```text
resources/agents/03-react-agent/
  agent.toml
  agent/
  ground_truth/
    manifest.json
    observations/defect-1/
      case.json
      run-1.zip
      run-2.zip
```

在此保留每轮的原始 Case、输入、Agent 输出、轨迹、Judge 报告、执行配置和人工笔记。每个 observation 的证据文件可以是包含完整观察的压缩包。建议用真实执行 ID 作为 observation ID，并在观察文件内保留 Suite/Attempt 身份。每个缺陷至少需要**同一 Case 的两轮不同观察**及人工确认。仅填写两个 ID 不能证明已复现；人工审核者仍需对证据的含义负责。

下面是示意 manifest，所有尖括号内容均需替换为真实值。哈希必须是 64 位小写十六进制字符串。

```json
{
  "schema": "abb.agent.ground_truth.v1",
  "agent_id": "react-agent",
  "defects": [{
    "id": "defect-1",
    "title": "<缺陷标题>",
    "expected_behavior": "<应有行为>",
    "observed_behavior": "<人工确认的实际缺陷>",
    "confirmed_by": "<审核人>",
    "confirmed_at": "2026-10-02T12:00:00Z",
    "source_sha256": "<Agent 执行源码哈希>",
    "case_sha256": "<参考 Case 文件哈希>",
    "observations": [
      {"id": "<第一轮执行 ID>", "case_sha256": "<同一参考 Case 文件哈希>",
       "evidence_path": "observations/defect-1/run-1.zip", "evidence_sha256": "<第一轮压缩包哈希>"},
      {"id": "<第二轮执行 ID>", "case_sha256": "<同一参考 Case 文件哈希>",
       "evidence_path": "observations/defect-1/run-2.zip", "evidence_sha256": "<第二轮压缩包哈希>"}
    ]
  }]
}
```

- `source_sha256` 使用被确认执行的 `plan.json` 中对应 Agent 注册记录的哈希。新建参考数据时，可以用 `agentbench.harness.session.plan.source_digest(unit)` 计算当前执行源码哈希；不能把新源码哈希写到旧版本产生的观察上。
- `case_sha256` 和 `evidence_sha256` 用导出的 `file_digest(path)` 对文件原始字节计算。Case 使用留存文件的哈希，不是 SDK 的语义 `content_sha256`。
- 证据路径相对 `ground_truth/`，必须留在该目录内。应独立保存完整观察，避免删除运行结果目录后丢失依据。
- `load_manifest(unit, agent_id)` 验证定义及证据文件哈希，并为每个缺陷增加 `ground_truth_sha256 = digest_json(原始缺陷记录)`。修改该记录会改变版本，使绑定旧哈希的评估失效。
- 根 `ground_truth/` 不影响执行源码哈希，也不会进入 ABB worker/SDK 的暂存构建副本。新生成的 `.dockerignore` 会排除 `/ground_truth/`；对旧 Agent 进行直接或手动 Docker 构建前，应补上该规则。上游自己的 `agent/ground_truth/` 仍是普通源码。不要把参考答案写进 `requirement.md`。

## 评估一次已保存的 Attempt

将明确判断写到 `<Suite 目录>/ground_truth/assessments.json`。待评估的生成 Case 可以与参考复现 Case 不同；审核者判断它是否暴露了**同一个缺陷**。它的 `case_sha256` 必须绑定自身保存的 Case 文件。

| 字段 | 含义 |
| --- | --- |
| `case_reproduced` | `true`：该 Case 暴露了指定缺陷；`false`：没有；`null`：尚未评估。 |
| `judge_detected` | `true`：保存的 Judge 报告正确指出了已复现的指定缺陷；`false`：没有；`null`：尚未评估。 |
| `ground_truth_sha256` | `load_manifest` 返回的参考缺陷版本。 |
| `result_sha256` | 完整已保存 Attempt result 的 `digest_json`，包含其中的 Judge 报告。 |

`judge_detected: true` 要求 `case_reproduced: true`。若 Case 已复现而 `judge_detected: false`，则记录一次 Judge 漏检。执行完成或 Judge 返回 `issue` 本身都不能代替上述判断。正面和负面判断都需要执行完成；Judge 判断还要求已保存报告。被拒绝或无效的执行证据不能成为有效评估。

以下开发者示例打印一个已验证的 sidecar 文档。检查证据后替换路径、ID、审核文字及判断值。示例只读取现有文件，不调用 Agent 或 SDK。

```python
import json
from pathlib import Path
from agentbench.harness.ground_truth import (
    ASSESSMENTS_SCHEMA, digest_json, load_manifest, validate_assessment,
)
from agentbench.harness.session.store import read_suite
from agentbench.harness.session.snapshot import suite_snapshot

unit = Path("resources/agents/03-react-agent").resolve()
suite = Path("results/suites/<suite-id>").resolve()
agent_id, defect_id, case_index, attempt_id = "react-agent", "defect-1", 0, "<attempt-id>"
plan, events = read_suite(suite)
snapshot = suite_snapshot(plan, events)
job = next(job for job in snapshot["jobs"] if job["agent_id"] == agent_id)
case = next(case for case in job["cases"] if case["case_index"] == case_index)
attempt = next(item for item in case["attempts"] if item["attempt_id"] == attempt_id)
defect = next(item for item in load_manifest(unit, agent_id) if item["id"] == defect_id)
assessment = {
    "agent_id": agent_id, "case_index": case_index, "attempt_id": attempt_id,
    "ground_truth_id": defect_id, "ground_truth_sha256": defect["ground_truth_sha256"],
    "case_sha256": case["prepared_case"]["artifact_sha256"],
    "result_sha256": digest_json(attempt["result"]),
    "case_reproduced": True, "judge_detected": False,
    "reviewed_by": "<审核人>", "reviewed_at": "2026-10-02T12:00:00Z",
    "rationale": "<具体观察到的行为，以及 Judge 报告如何指出或遗漏该缺陷>",
}
validate_assessment(assessment, {"plan": plan, "snapshot": snapshot, "directory": suite},
                    {(agent_id, defect_id): defect})
print(json.dumps({"schema": ASSESSMENTS_SCHEMA, "suite_id": plan["suite_id"],
                  "assessments": [assessment]}, indent=2))
```

若 sidecar 已存在，保留其他评估并添加新记录，再原子替换完整 JSON 文件。完全相同的重复记录只计一次；同一 Agent、Case slot、Attempt 和缺陷的冲突判断会被拒绝。加载器检查 Suite 身份、Agent 源码哈希、留存 Case 字节、精确 Attempt result 和参考版本。这些检查验证关联及完整性，不会独立判断人工结论是否符合事实。

## Overview 统计语义

- 在全部有效历史 Suite 中，每个 Agent 的每个当前参考缺陷只计一次。Reuse 和 retry 增加观察，不增加已知或已发现缺陷数量。之后重试不会抹掉此前有效的发现。
- 有一条有效记录同时包含两个判断，该缺陷才算完整评估。部分评估仍会展示。有任一有效 `true` 就说明历史上复现或发现过；否则保留明确 `false`，没有判断时为 `null`。
- `discovery_rate` 的分母是全部有效已知缺陷。至少一个缺陷被完整评估后才提供比例；未知或未配置的数据不会被显示为 0%。
- 缺少 manifest：`not_configured`；空 manifest：`empty`；无判断：`not_assessed`；部分覆盖：`partially_assessed`；所有缺陷完整评估：`assessed`。无效定义或关联会产生警告，并排除在有效结果之外。
- `GET /api/benchmark/overview` 是只读接口。修改参考文件或评估后即可重新读取，不要求新增 Suite event。没有 canonical provenance 的旧 Suite 仍保留执行统计，但不能提供经验证的 GT 评估。

JSON 文档上限为 2 MiB，每个证据文件上限为 64 MiB。该接口不会生成 Case、调用 Judge、补采观察，也不会自动判定 Case 生成质量、Judge 准确率或误报率。
