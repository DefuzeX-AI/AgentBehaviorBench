你的方向是对的。我建议设计成：从 .env 读取“最多同时运行几个 Agent”，由主机统一调度，每个任务使用独立的容器组。
关键不是简单加一个线程池，而是让任务的状态、网络、日志和清理都各自独立。我检查了当前代码，也查了 Python 和 Docker 官方资料，现有结构可以支持这个方向。
1. .env 应该设置“Agent 并发数”
建议新增：
# 同时运行的 Agent 任务数
ABB_MAX_PARALLEL_AGENTS=4

# 同时构建的 Docker 镜像数
ABB_MAX_PARALLEL_BUILDS=1
这些是拟新增配置，现在还未实现。
这里不叫 THREAD_COUNT，因为一个任务内部已经有读取日志、接收 Trace 等辅助线程。用户真正关心的是“同时跑几个 Agent”，而不是整个程序有几个线程。
具体行为：
- 有 100 个 Agent，先进入等待队列。
- 最多启动 4 个。
- 任意一个完成，立即补上下一个，不必等这一批全部完成。
- 未设置时默认 1，保持现在的串行行为。
- 非整数、零、负数直接报配置错误。
- 启动时统一读取配置，运行过程中不反复读取 .env，也不在线程里修改全局环境变量。
并发数属于 ABB 的调度配置，不要放进 sdk_options，否则未来接 Panda 时又得重复实现。
2. 一个并发任务，实际上是两个容器
准确说，不是启动多个 Docker Engine，而是在同一个 Docker Engine 下启动多个容器。
你目前的代码已经是：
一个任务拥有的资源	用途
Agent + SDK 容器	运行 Agent、KUMA，采集执行证据
专属 interceptor 容器	拦截模型和其他允许的网络请求
独立网络空间	隔离不同任务的网络规则
独立目录	保存输入、Case、Trace、Judge 和 .kuma 状态


因此，4 个正在评测的任务，通常对应 8 个运行容器，而不是 4 个。
网络拦截会不会串？
当前实现的基础是合理的：[runtime.py (line 117)](C:/Song_startup/benchmark/AgentBehaviorBench/agentbench/runtime/docker/runtime.py:117) 为每次执行生成独立名字，并让 Agent 加入它自己那一个 interceptor 的网络空间：
Agent A → interceptor A
Agent B → interceptor B
使用的是：
--network container:<本任务的 interceptor>
Docker 官方支持这种“两个容器共享一个网络空间”的方式。Docker 网络文档
所以，两个 interceptor 都监听 8080 不构成冲突：它们位于不同网络空间，而且当前没有把它们发布到同一个宿主机端口。
我建议保留这个结构：
- 不让所有 Agent 共用一个 interceptor。
- 不改成宿主机网络。
- 每个任务继续独立生成证书、临时 token、网络规则和结果目录。
这解决的是结构上的隔离；还需要并发测试证明请求和 Trace 没有串任务。
3. 并发入口应该放在 SuiteRunner
目前 [SuiteRunner (line 170)](C:/Song_startup/benchmark/AgentBehaviorBench/agentbench/harness/runner/suite_runner.py:170) 是外层遍历 Agent、内层遍历 Case。
第一版建议只并行外层：
- 不同 Agent：可以并行。
- 同一个 Agent 的多个 Case：先保持串行。
- 同一个 Case 的多个 Input：必须按顺序执行。
这样不会一次把“Agent 并行、Case 并行、对话步骤并行”全部引入，尤其不会破坏连续对话的状态。
主机这部分主要等待 Docker 和网络，因此可以用 ThreadPoolExecutor 做首版调度；真正的 Agent 计算已经在不同容器进程中，不需要为了它再套一层主机进程池。
但 Python 官方明确提醒：线程池中正在执行的任务，不能靠 Future.cancel() 强行停止，退出时还会等待工作线程。因此，可取消、有限时的 Docker 控制流程，是使用线程池的前提。Python 并发文档
4. 在启动并发前，需要补好四件事
① 每个 Agent 创建独立 runner
现在 SuiteRunner 持有一个 _benchmark_runner。
而 KUMA runner 里面有这些可变状态：
self._case_batches
self._case_fingerprints
prepared["next_index"]
它们虽然按 Agent ID 做了一部分区分，但目前没有“同一个 runner 可以被多个线程同时调用”的保证。
因此，我建议：
共享不可变的配置，每个 Agent 任务通过适配器工厂创建自己的 runner。

未来 Panda 也走相同流程，不在调度器里面判断：
if sdk_name == "kuma":
    ...
对于 Python 用户直接传入的现成 SDK/runner，也不能擅自共享或复制。没有独立实例创建方式、没有明确并发保障时，保留串行或清楚报错。
② 工作线程不直接打印，统一汇总事件
这是我认为与你的网页 Trace 最相关的改造。
现在的 LLMActivity 有“当前阶段”“当前调用”等状态，新阶段还会清空旧状态。即使加了锁，多个 Agent 也可能互相覆盖显示。
建议改成：
每个任务发送带身份的事件 → 线程安全队列 → 一个统一的结果写入和显示入口。

事件要能区分：
suite_id / job_id / agent_id / case_id / call_id
不能靠“当前正在运行哪个 Agent”去猜归属。Python 的 queue.Queue 就提供了线程间安全交换数据的基础。Python 队列文档
原始 Trace 仍写各任务自己的文件，队列主要传进度和文件引用，避免把大量响应正文都堆在内存里。
另外，当前结果文件已经有写锁，不是完全没有保护；但每次都重写整个 JSON，100 个 Agent 时会放大开销。第一版可以保留现有查看器格式，同时合并高频进度更新。
③ 镜像构建单独限流、去重
目前逻辑是：
检查镜像不存在 → 构建
多个任务同时启动时，可能都发现公共 interceptor 镜像不存在，然后一起构建。
需要增加：
- 相同镜像指纹只允许一次构建，其他任务等待结果。
- 公共 interceptor 镜像可以预先准备。
- 构建并发与 Agent 运行并发分开限制。
这样 4 个评测并发，不意味着同时进行 4 次高开销构建。
④ 超时、取消和清理必须属于任务自己
现在的评测超时主要从 session.wait() 开始计算，前面的镜像构建和部分 Docker 命令并没有完整超时保障。
需要明确覆盖：
构建 → 启动 → 执行 → 日志收尾 → 清理
每个阶段都有限时；排队时间不算执行超时。
用户按 Ctrl+C 时：
1. 停止派发新任务。
2. 取消还在排队的任务。
3. 请求正在运行的任务停止自己的容器。
4. 保存已有结果和 Trace。
5. 只清理属于本次任务的容器、网络和临时文件。
Docker 支持先发停止信号、宽限期后强制结束。Docker stop 文档
**停止本地容器不代表撤销已经提交给远端的 Judge，也不代表退回费用。**因此不能在出错后盲目重跑整个 Case。
5. 你这台机器，先从 2，再到 4
我只读检查了 Docker 当前可见资源：
- 16 个 CPU。
- 约 15.6 GiB 内存。
现有配置给每组容器设置的上限是：
- Agent：1 CPU、1 GiB。
- interceptor：1 CPU、512 MiB。
所以 4 组运行任务的内存上限合计约 6 GiB，还需要给镜像构建、Docker、日志和其他程序留余量。这是配置上限，不是实际占用，也不是预留资源。Docker 资源限制文档
我的起步建议：
先用 2 并发验证隔离和取消，再用 4 并发观察内存、耗时和限流情况。

别直接设成 100。容器隔离不会隔离账户额度；多个任务仍可能共用 KUMA、OpenRouter、Tavily 的账户限制。OpenRouter 的 429 也可能来自上游模型提供方。OpenRouter 限流文档
我建议第一版的范围
单机、Agent 间有界并发、每任务独立 runner 和容器组、统一事件汇总、可靠取消清理。
验收不能只看“两个任务都跑完”，还要验证：
- 两个任务的 Case、输出、Trace、Judge 不串。
- 一个失败，另一个继续。
- 同一个镜像不会重复构建。
- Ctrl+C 后没有遗留本次任务的容器。
- 乱序完成可以即时显示，但最终结果仍按 Agent 注册顺序汇总。
- 并发数为 1 时保持现有行为。