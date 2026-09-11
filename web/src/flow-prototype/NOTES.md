# 执行流程 UI 原型

待确认的问题：流程地图、时序泳道、聚焦阅读，哪种方式最容易理解一次真实运行？

启动：在 `web/` 执行 `npm run dev -- --port 5174`，打开
`http://127.0.0.1:5174/?variant=A#view=flow`。A/B/C 可从浮动栏或顶部选择器切换。
页面使用当前 Run 的只读 API，手动更新快照。原有时间线保留。

- A：Case/Input、Agent 根调用、结果与评测的空间地图；展开子调用时折叠没有交互的单分支包装层。
- B：按时间向下阅读，SDK、Agent、LLM、Tools 四条泳道；完整调用聚合显示。
- C：调用导航、当前内容、直接子调用三栏，沿路径逐层阅读输入输出。

实线来自同一 trace 的父子关系；虚线为 Input 或 framework span 关联，点击可看证据。
未关联调用单独保留，不能把同名工具、时间接近或模型返回的工具请求当成执行证据。
SDK/Judge 的全局快照可查看，但没有 Input ID 时不为它们添加流程边。

新增 Agent/SDK 可以在 `abb.invocation.v1` 中提供可选的 `observation_context`：
`{ "case_id": "...", "input_id": "..." }`。这不改变传给 Agent 的 `input`。
worker 会把这两个 ID、实际 invocation_id、agent_id 写入 framework JSONL 及结果；
OTel spans 保存 `abb.case_id`、`abb.input_id`、`abb.agent_id`。
KUMA adapter 从 SDK 原始 Input 快照填入这些字段，其他 SDK 也可使用同一约定。
已有 parent_span_id 和开始/结束事件继续作为调用和时间依据；旧记录不补造新字段。

待用户看过后记录选择：____。选定后将胜出布局整理为正式页面，再删除其他原型布局。
