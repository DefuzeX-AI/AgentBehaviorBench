# 多终端并行运行

可以在两个终端分别启动独立进程。每次运行创建新的 Suite ID，各自保存 Case、Attempt、SDK Run 和结果；容器及网络也使用独立名称。本轮已观察到两个 Suite 的不同 Agent/拦截器容器同时运行，第三个进程无法取得它们的写入锁。双进程共 12 个 Case 均收到并保留 Judge 报告；其中一轮记录了一次 OpenRouter 连接中断，不能称为完全无错误。详见 [双进程验收记录](Parallel-Terminal-Acceptance-2026-09-14.json)。后续测试已按用户要求停止。

## 启动两轮新测试

两个终端都进入项目目录并激活 `.venv`。`run` 使用 `resources/registry.toml` 中启用且为 `ready` 的 Agent，以及各自的 `case_count`。

终端 A：

```bash
ABB_MAX_PARALLEL_CASES=3 agentbench run --yes --no-view --output results/parallel-a/result.json
```

终端 B：

```bash
ABB_MAX_PARALLEL_CASES=3 agentbench run --yes --no-view --output results/parallel-b/result.json
```

`--yes` 跳过初始确认，`--no-view` 不启动网页。以终端打印的 `Result artifact` 路径为准：当前持久化结果位于对应目录的 `suites/<suite_id>/events.json`。

worker 上限是**每个进程单独计算**的。上面两轮各有足够 Case 时，合计最多同时调度 6 个任务；它们共享机器资源和 API 额度，没有跨进程的总并发上限。单轮实际 worker 数不超过该轮 Case 总数。

## 用同一批 Case 比较两轮结果

把下面的 `suite_original` 替换为已有 Suite 的实际目录。分别在两个终端执行：

```bash
agentbench reuse results/suites/suite_original --output-root results/compare-a
```

```bash
agentbench reuse results/suites/suite_original --output-root results/compare-b
```

两轮保留相同 Case ID 和输入文件，创建不同 Suite、Attempt 和 SDK Run，不重新调用 CaseGen。`reuse` 默认沿用原计划的模型、SDK 参数及 worker 数；临时改变 `ABB_MAX_PARALLEL_CASES` 不会覆盖已保存的 worker 配置。详见 [Case 复用说明](Case-Reuse-Commands.md)。

## 锁、镜像与网页

- **同一个 Suite 只能有一个写入进程。** 第二个 `resume` 或 `retry` 会被拒绝；需要独立实验时使用 `reuse` 创建新 Suite。
- **启动阶段有短暂的共用锁。** 同时复制同一个源 Suite，或同时创建、登记 Suite，可能提示另一个操作正在进行。等该操作结束后重新执行启动命令即可；这把锁不会覆盖整轮测试。
- **镜像缓存共用。** 相同构建输入复用同一个镜像标签。构建协调锁只覆盖单个进程；两个进程同时发现缓存缺失时，仍可能各自提交构建。
- **网页端口自动避让。** 默认绑定 `127.0.0.1:8765`，绑定失败时改用系统分配的空闲端口。`reuse` 不自动启动网页，可另开终端运行 `agentbench view <实际 events.json 路径> --port 0`，再打开它打印的地址。
