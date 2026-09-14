# Issue 修复状态与验证范围

对应 [31 个 Issue / 18 个 PR 的审查基线](Upstream-Issue-Review-2026-09-14.md)。
代码回归通过不代表真实服务最终验收完成。真实 ReAct 首次运行因 OpenRouter
凭据 401 失败；Case 与 Judge 已保存。当前成功 0 / 尝试 1，详见
[运行记录](Benchmark-Repair-Campaign.md)和 [Ledger](Benchmark-Campaign-Ledger.json)。

| Issue | 当前处理 | 验证或限制 |
| --- | --- | --- |
| #7 | 按 PyPI 0.2.4 create_run/save_case/case_path 协议生成与复用 | test_issue7；真实服务成功生成并加载首个 Case。 |
| #8 | 沿用精确 release-check whitelist，无须套用旧 PR22 | test_issue8；真实 release GET 200，其他 GitHub API 未放开。 |
| #9 | 保留 source/target host、调用 ID、HTTP 状态，去掉 query/fragment | test_issue9；不是本轮新增的 runtime 修复。 |
| #10 | GraphBubbleUp 控制流关闭 span，不作为 ERROR | test_issue10；真实 LangChain 工具参数/结果证据亦覆盖。 |
| #11 | 旧 sdk_source 路径方案已退出；插件独立 PyPI requirements | test_kuma_pypi 的安装/旧选项拒绝检查。 |
| #12 | run 支持显式 --yes | test_issue12。 |
| #13 | ReAct profile 已用 basic-safety-research@1 | 本次官方服务成功生成 Case；未重新引入 BASE-05。 |
| #14 | 二次 Docker 清理超时不泄露 argv/密钥 | test_issue14；安全异常替换并抑制原 traceback context。 |
| #15 | evaluate 汇总所有 Judge，行为 issue 不再退出 0 | test_issue15；实际失败运行退出 1。 |
| #16 | 不恢复已淘汰的 SDK 源码 CLI 参数 | test_kuma_pypi。 |
| #17 | viewer 路径、端口、启动错误转换为明确诊断 | test_issue17。 |
| #18 | evaluate/certify 拒绝确认时不执行 | test_issue18。 |
| #19 | 配置错误在 CLI 层处理，保留 Python API 原异常契约 | test_issue19。 |
| #20 | 失败 Case 保留匹配身份的 Judge/artifact，不伪造成功结果 | test_issue20、test_issue20_evidence；真实 401 失败后的 Judge 已保留。 |
| #31 | Docker 边界不注入宿主 callback 对象 | test_issue31、真实目录插件容器验收。 |
| #32 | 关闭 stdin 不抹掉已完成 execution，viewer 仍清理 | test_issue32。 |
| #34 | 原 SDK code/request ID 与相关网络错误分别展示；保留公开请求恢复入口 | test_issue34、test_issue34_recovery；真实中断恢复仍未做收费验收。 |
| #36 | 已记录的连接/上游终态与采集/策略等致命错误分开 | test_issue36、Docker 并发/取消验收；未从字符串猜测用户主动取消。 |
| #37 | viewer 启动信息立即 flush | test_issue37。 |
| #38 | 补评测目标、结果含义和可运行结果示例 | README、Troubleshooting、真实执行的 offline_demo。 |
| #39 | 说明 adapting/ready；新增两个 Agent 与接入记录 | test_issue39、真实断网镜像检查；真实 certify 未完成。 |
| #40 | Docker 前置条件与官方平台安装入口 | README；断网本地 demo 明确无需 Docker。 |
| #41 | 安装后 sdk list 验证与预期结果 | README；目录发现测试无需凭据。 |
| #42 | 说明三类凭据用途和官方入口 | README；模型 slug 不是密钥，不编造 Kuma 发放入口。 |
| #43 | KUMA_API_KEY 非空优先，DEFUZEX_API_KEY 为 ABB 别名 | test_issue43；仅记录变量名。 |
| #44 | 增加真正无账号/网络/Docker 的本地示例 | test_issue44；明确使用离线 Provider。 |
| #45 | 模板模型值不等于运行时默认 | README、中文指南。 |
| #46 | 修复翻译相对路径、补 CLI/onboarding/中文操作指南 | test_issue46 校验入口文档链接；深入设计仍以英文为准。 |
| #47 | 中文目录图改为真实目录结构 | 中文 README。 |
| #48 | 补环境、网络、证据、Judge 和失败结果排错表 | Troubleshooting、中文指南。 |
| #49 | 解释 ABB / Kuma / DefuzeX 服务职责 | 仓库文档已补；外部产品网站未修改或宣称修复。 |

文档问题通过可运行示例和链接校验覆盖，没有为每段静态文字编造一个字符串断言。
关键运行错误分别放在 test_issue 编号文件。旧 PR 涉及已删除路径和旧 SDK 合同，
采用当前架构实现与回归，不整批合入旧代码，也未向上游发送评论或合并 PR。
