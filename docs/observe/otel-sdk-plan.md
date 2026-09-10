# OTel 可视化与真实 KUMA SDK 接入实施计划

> 最新用户决策（2026-09-09）：暂不实现题面兼容性检查或拒绝。SDK 的 payload 原样交给现有 Adapter，不解析、不提取、不改写；现有 LangGraphAdapter 对文本按 input_key 包装。以下旧计划中“严格输入合同/不兼容停点”的要求被此决策替代。记录真实输入、输出和异常，由 Judge 判断行为，不把执行成功当成题意完成。

## 范围与协作边界

- 复用 Runtime、Adapter 和 Company 外层 binding，不改上游 Agent。
- 不修改 services/model-interceptor、runtime/interception、网络协议/路由/认证与网络采集逻辑；这些由另一位 Agent 负责。
- 新代码放在 observe/otel、evaluation、web 的独立模块。共享 Worker、ObserverFactory、Dockerfile 仅做最少接线，动手前检查已有修改。
- SDK 使用本地 Defuze-SDK 的 kuma 包，正式验收必须真实调用官方服务；离线测试只做回归，不能替代正式验收。
- 密钥从 .env 读取，不打印、不写入镜像。真实验收限定一个 Case，不自动重复生成或重新执行付费任务。
- 用户已明确授权 KUMA 官方 SDK 网络访问（2026-09-09）：允许官方 `https://defuzex.ai/api/agentdefuze` 接口及其所需子路径/请求方法；不得将这些 SDK 请求转发到模型。此项是授权记录，不代表网络规则已生效；仍由网络负责方接线并验证，不放开无关域名。
- 执行、证据完整性、SDK 提交和 Judge 判决分别记录。Tavily 返回 failed_results 是行为，不自动把已返回报告判成执行失败。

## 1. 基线与记录

检查工作区、记录测试基线及相关文件；仅检查凭据是否存在，不输出值。
验收：计划已落盘，现有修改保留，网络相关文件未被本任务改动。

## 2. OTel Provider 与文件导出

在 Agent 进程配置独立 Provider；若存在兼容 Provider 则复用，不重置全局状态。
现有框架事件同时进入 ABB JSONL 与真实 OTel spans。显式映射父子关系，避免异步并发串线。
文件 exporter 在 span 结束时落盘；原始输入/输出等大内容单独保存，以引用关联，不能依赖有限长 span 属性保存全文。
关闭执行前 flush；失败和未结束步骤明确记录。无 KUMA 也能采集。

验收：嵌套、并行、异常、两个独立运行、Unicode、大于 256 KiB 的载荷均测试；无重复执行、父子正确、保存内容相等。真实 Company Docker 离线图跑出 OTel 文件。SDK/真实服务未参与这一阶段。

## 3. 网页 OTel 视图

提供调用树、耗时、状态、span 详情、载荷按需读取。原始事件和 OTel 视图并存。
数据接口限制在本地运行目录内，防止路径越界；分页与载荷按需加载，不以 20 MiB 拒绝完整运行记录。
历史无 OTel 的记录明确提示，不能把旧 JSONL 伪装成运行时 OTel。

验收：真实 OTel 文件可展示父子调用和详情；大文件仍可分页查看；恶意内容只显示为文本；无越界读取；浏览器实测。

## 4. 容器内真实 SDK 与 Company 执行闭环

复用已完成的同容器安装验收，将其升级为公共评测 Worker，而非往 LangGraphAdapter 中塞 SDK。
循环：kuma.create_run → get_input(full=True) → 输入契约校验 → 现有 Adapter → submit(output)。
明确使用 agent_profile_path/max_steps 等当前接口；正式模式不用 allow_local 绕过容器要求。
Company 只接受公司及可选网址/行业/总部字段。官方文本 Case 必须具有可忠实映射的输入合同；不能把任意指令直接当公司名。若官方 Case 形状不能兼容，停在生成/预检阶段，请用户选择测试合同，不能自行换自定义 Case 冒充官方生成。
网络/凭据接线若必须修改其他 Agent 负责的文件，先协作确认，不覆盖。

验收：真实 SDK 官方 Case/Input、真实 Company 返回值、SDK History/Submission 三者可对应；每 Input 只提交一次；输出与本地报告一致；容器非 root/只读根保持不变。

## 5. KUMA Evidence 与真实 Judge

同一个 OTel Provider 挂 KUMA capture；ABB 原始 spans 和每步 SDK Evidence 分开保存。
保存 Case、每个 Input、原始/映射输入、执行结果、Submission、Evidence、Judge Report、错误阶段与关联 ID。
提交后 Judge 失败不得重复 submit；依据 SDK state/history 判定后续动作，付费重试需明确边界。

验收：一个真实官方 Case 完成提交并得到真实 Judge 报告（不要求 pass）；Evidence 有真实 spans；各 Input 不串证据；SDK 过滤/限额不影响原始记录；SDK 错误与 Agent 执行状态分离。

## 停点与交付

每阶段记录实际检查及结果。缺 KUMA 凭据、官方输入合同不兼容、共享网络接线未确认、官方服务拒绝/额度不足时明确停点，不用 mock 宣称完成。
最终报告必须分别列出：离线测试、真实 Docker、网页检查、真实 SDK/模型/Judge 调用；不能把 import 验收当作执行验收。

## 当前进度

- [x] Company 与 kuma 同容器同解释器 import 已验收（前序工作）。
- [x] 本实施计划已记录。
- [x] OTel 采集与原始文件导出：4 项测试通过；真实 Company Docker 离线执行通过，otel-status 为 complete，unfinished_spans 为 0。
- [ ] 网页 OTel 视图与大数据按需读取。
- [ ] 真实 SDK/Company 提交闭环。
- [ ] 真实 Judge 与 Evidence 验收。

### 实施记录（2026-09-09）

- 已实现独立 `evaluate` 命令、临时镜像叠加、同进程 SDK Worker、原样 payload 转发、共享 Provider、逐 Input Submission/Evidence 留档；尚未通过完整官方验收。
- SDK 要求仓库与请求账本同文件系统：正式运行目录保留实际源码副本 `sdk-repo/`，只读挂到 `/opt/agent/agent`，仅 `.kuma` 子目录可写。构建副本预置忽略规则，不修改用户原源码或网络实现。
- 已通过真实 Docker 断网验收：原始 Company 图 + 真 KUMA SDK + OTel + 本地 Case/Judge，61 个 spans；产物保留在 `results/observe/acceptance-company-sdk-offline`，明确标记 OFFLINE，不能当官方生成/判决。
- 浏览器实测已打开上述 OTel 树、根节点完整输出和 SDK 页面。Vite/preview 新增评测产物及原始事件分页；单条大于 20 MiB 的事件完整读取测试通过。旧兼容接口和手动导入的大小限制尚保留，不影响新的运行分页视图。
- Python view 的单运行 API 已接 OTel、SDK、分页原始事件；回归验证与 Vite 区分记录。
- Python view 浏览器验收通过：`http://127.0.0.1:8766/` 展示离线运行的 61 个 OTel spans 和完整父子树；Vite `5173` 也已实测展开根节点完整报告。真实 Docker 离线最终回归 1 项通过（10.50s），Python 聚焦回归与网页测试结果见本轮交付。
- 官方尝试 `7a092bf6ed6e472882a14d8c30244ff2` 已从 Company 容器访问 KUMA，但被服务拒绝：`PermissionDeniedError / forbidden`，提示“此密钥为只读密钥，无法生成 Case 或运行 Judge”。未生成 Case、未执行真实研究、未取得官方 Judge。已请用户更新有写权限的密钥，不重复调用。
- 之前两次尝试仅在本地 SDK 文件系统初始化失败，已修复，未进入官方生成。不能与上述离线成功记录拼接成正式通过。

## 2026-09-09 复核：最终闭环实施顺序

本节细化以上计划，不代表以下功能已经实现。本轮复核代码并更新计划，不启动付费 Case。

### 对照代码后的结论

| 环节 | wangyi 当前实现 | ABB 当前缺口与决策 |
| --- | --- | --- |
| 公共执行器 | `wangyi/tools/case_exec.py` 为多个 Agent 共用，专属输入映射放 entrypoint | 保留 Registry / AdapterFactory / binding；新增公共 evaluation 层，不给每个 Agent 复制 SDK 循环 |
| 官方生成 | `tools/case_gen.py` 单独出题；case_exec 读取保存的题，使用自定义 Provider + 官方 Judge | 本次必须在容器里以官方 Provider 创建 Run，生成的 Case 在同一 Run 内执行、提交、Judge，不用保存题的自定义重放替代 |
| Company 输入 | 015 的 `case_payload` 明确注明失真：整段题面塞进 company | 提供真实能力 Profile + 显式输入合同，严格检查公司/网址/总部/行业；不可投递的题保存后停止，不伪装成忠实执行 |
| OTel | 015 `build_tracer` 将原始 exporter 与 KUMA capture 挂到同一个 Provider | ABB 已有运行时 spans 和文件 exporter，但尚未连接 KUMA capture；必须显式注入同一个 Provider |
| SDK 运行位置 | case_exec 的 Agent 调用和 SDK 同进程；容器内运行 | ABB Company+SDK 目前只是独立验收镜像能 import，常规执行 Worker 尚无 SDK 生命周期；旧 `sdk/defuzex.py` 仍使用旧导入与参数 |
| 留档 | 保存原始 spans、报告，但部分 L2 文件只保存末次 submission；历史摘要会截断 | ABB 保存每个 Input 的 Evidence/Submission，完整原始数据独立留档；不复制截断历史或原地修改 Agent 客户端的做法 |
| 网页 | `wangyi/view/agent.html` 分开显示 Judge、L2 与懒加载 L1 | ABB 已有 OTel 树组件；仍需浏览器验收、评测产物接线、完整分页。旧原始事件接口仍有 20 MiB 限制，不能宣称已解决 |

### 目标执行结构

```text
宿主机：选择 Agent → 配置/凭据预检 → 复用 DockerRuntime / DockerSession
└─ 一个 Agent 容器、同一个 Python 进程
   ├─ EvaluationWorker：创建一次 Provider + KUMA capture
   ├─ kuma.create_run（官方 Case Provider、官方 Judge、allow_local=False）
   ├─ 每个 Input：合同校验 → AdapterFactory → LangGraphAdapter → Company
   │             └─ 活跃框架回调 → 同一个 OTel Provider
   │                              ├─ ABB 完整文件 exporter
   │                              └─ KUMA Evidence capture
   └─ 结束当前 Input spans → flush → submit(真实 output) → 最终 Judge
宿主机：保留产物/诊断 → 网页显示 Case、执行、OTel、Evidence、Judge
```

网络 Interceptor 保持独立。其网络事件不是本进程 OTel spans；可用现有相关 ID 联查，不将网络 JSONL 重放伪装为 KUMA 捕获。KUMA 请求仅访问官方服务，不走模型改写。

### A. 先固定公共合同及正式入口

- 新建 `agentbench/evaluation/contracts.py`：评测请求、阶段状态、关联 ID、产物目录合同。
- 新建 `agentbench/evaluation/input_binding.py`：注册式 Case Input 转换接口；默认支持忠实原样 JSON/文本输入，特定映射只在 Agent 外层绑定中声明。
- Company 增加独立的 `evaluation/profile.md` 与输入合同，不修改上游代码；Profile 描述固定研究流程而非可执行任意指令的通用助手。
- 首次验收一条官方 Case、`max_steps=1`，先验证真实单步闭环；公共循环支持多个 Input，但 Company 当前不宣称多轮记忆，不拼接或截断历史假装会话。
- 建议新增独立 `evaluate` 命令，沿用 observe 的编号选择体验，例如拟议 `python -m agentbench evaluate 1 --cases 1 --max-steps 1`。此命令尚未实现；observe 继续免 SDK，旧 run/certify 的迁移另行处理，不静默改变默认行为或认证状态。

验收：有效结构保留所有字段；多余指令、丢字段、非法形状明确拒绝；选择只发生一次；预检不会产生付费请求。原始官方 payload 与映射值均留档。更新 CLI 文档及解析测试。

### B. 将 SDK 安装验收升级为正式容器交付

- 新建 `agentbench/evaluation/image.py`，提取现有 `tests/acceptance/company_sdk` 的安全源码打包能力，复用现有镜像构建器，不另写 Docker 管理器。
- 新建 `agentbench/evaluation/service.py`：宿主机只调度，不 import Company、不调用官方 SDK 生成 Case。
- 将本地 SDK 与 Company 安装进同一解释器，保存 SDK 版本/源代码指纹、Agent revision、镜像 ID、进程 PID 和容器标识。
- 只对实际 Agent 仓库内 SDK 所需 `.kuma` 状态目录提供专用可写挂载；验证 SDK 是否还需其他路径。不得传一个空的无关 repo 冒充 Company，也不得因此放开整个只读根。
- 凭据只在运行时注入；优先 `KUMA_API_KEY`，兼容显式读取 `DEFUZEX_API_KEY` 传入 `api_key`，不复制 `.env` 进镜像。
- 网络负责方接入已授权 KUMA 路由。预检域名、TLS、方法及子路径，保留认证，不转发模型；未接通时停止正式出题。

验收：真实 Docker 内同解释器 import；非 root、源码/输入不可写、SDK 状态和结果可写；密钥不在构建上下文或产物里；SDK 官方接口可达且无模型改写。不得用宿主机 SDK 或不限网络容器替代。

### C. 公共 Worker 与同 Provider 证据

- 新建 `agentbench/evaluation/worker.py` 与 `agentbench/evaluation/kuma_session.py`，分别负责执行编排、当前 KUMA API/序列化/状态处理。
- 从现有执行 Worker 复用 Agent 加载和调用边界，提供显式 Provider/Observer 注入；不复制图执行逻辑，不从容器内再进入 Docker 分支。
- Provider 在 Case 开始时创建一次，KUMA `configure_trace_evidence(provider)` 在 Agent 执行前挂载；每个 Input 的 OTel 根 span 完成并 flush 后才提交。
- ABB 当前仅写 `abb.*_ref` 的全文引用，不能假设 KUMA 会读取这些文件。按 SDK 实际允许的 OTel 属性映射工具名、操作等必要语义；显式 `submit(output=...)` 提交真实报告，并验证最终 Evidence 内容。
- 每个 Input 独立文件 exporter / 关联 ID，结束 Input 不关闭共享 Provider；Case 结束才统一关闭 capture、Provider 和 Adapter。

验收：真实异步离线图产生父子/并行 spans；同一 Provider 被 KUMA 实际捕获，Evidence 非空且含预期 Agent/工具行为，而不只是根 span；两个 Input 不串证据；异常仍 flush。ABB 全文文件与原值相等，KUMA 的白名单/限额与 dropped 信息单独显示，不绕过 SDK 安全限制。

### D. 官方生成、一次提交与 Judge 状态机

- 官方调用使用当前 `kuma.create_run(agent_profile_path=..., trace_evidence=..., max_steps=1, allow_local=False, save_local=True, track_files=False)`，不传自定义 Case/Judge Provider。
- 创建 Run 后立即保存官方 Case/身份信息；按 get_input → 执行 → submit 的严格握手进行。
- 每次提交前保存输出与关联信息，提交后保存对应 history、submission、evidence。最后一次提交可能同步触发 Judge，必须在异常分支仍保存已提交 history。
- 区分生成失败、输入不适配、执行失败、证据失败、提交失败、Judge 失败。已进入 history 的 Input 不再次 submit；请求结果不明时记录 SDK request/operation 信息，不重新 create_run 出另一题。
- SDK 的幂等传输重试按其契约使用；不增加外围付费重跑循环。额外 Case 或新的 Judge 重判另行明确授权。

验收：一个真实官方 Case 具有可追踪 case_id；Company 真正执行并产生报告；每个 input_id 恰好一份提交；提交 output 与报告一致；拿到官方 report_id/判决。Judge 可以为 issue 或 insufficient_evidence，链路完成不等于 Agent 质量合格；但 Evidence 空/串线仍属于本次集成验收失败。

### E. 网页展示及最终真实验收

- 新建网页独立评测模块，与现有 OTel 组件复用，不把页面全部堆入 App.jsx。
- 同一运行页依次展示 Case/Input、Company 原始报告、OTel 调用树/耗时/输入输出、每步 KUMA Evidence、官方 Judge 报告。
- 原始记录分页，全文按需读取；同步补齐 Vite 服务与 Python viewer 的路由能力，不能只有开发端口能看。
- 明确显示执行状态、OTel 完整性、SDK 提交状态、Judge 状态四项，旧运行没有 OTel 就提示没有，不能伪造。

验收：真实浏览器从运行列表打开最终验收 run，展开一个研究节点及工具输入输出，查看同一 Input 的 Evidence 和 Judge；刷新后仍能读取。超过 20 MiB 的运行记录能浏览，全文载荷不截断；路径越界和恶意 HTML 测试通过。

### 最终产物与通过条件

建议新评测运行根为 `results/evaluate/<run_id>/`，网页运行索引显式兼容此类型：

```text
manifest.json                 版本、容器/进程、ID、四项状态、各产物引用
case.json                     官方生成的 Case
inputs/<input_id>/
  input.json / mapped-input.json / result.json
  framework.jsonl / otel.jsonl / otel-status.json / otel-payloads/
  submission.json / evidence.json
judge/report.json             官方 Judge 报告
diagnostics/                  SDK 阶段错误、容器诊断、网络记录引用
```

验收报告必须提供可打开的运行目录和网页入口，并逐项证明：同容器同进程、官方生成、实际 Company 输出、完整 OTel、真实 KUMA Evidence、官方 Judge。任何一项缺失均标记未完成。当前只完成前序 OTel/Docker 离线部分，尚未达到此最终条件。
