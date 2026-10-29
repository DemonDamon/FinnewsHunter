# Agent-First 金融领域后台

本文件对应 [Master Plan](../../.cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md) 与 [S00 实施子计划](../../.cursor/plans/2026-10-29-finnews-s00-baseline-contract.plan.md)。2026-10-29 用户已确认方向并授权逐批实施。S00 已通过本地独立复审，S01 最小装配正在实施；所有改动尚未远端合流，不宣称研究后台已经完成。

## 产品定位

FinnewsHunter 为金融领域后台，Near 为唯一日常用户入口，AGX 提供通用智能体运行、工具连接和扩展底座。后台能力优先设计为结构化、可授权的工具，不意味着所有确定性逻辑交给自由行动的模型。

保留 FinnewsHunter 仓库名及遗留前端。首期不新建应用、研究控制台、金融版客户端、身份平台或网关，不另启生产 MCP 服务。既有 FastAPI `app.main:app` 在后续 S03 挂载 `/api/v1/mcp`；PostgreSQL 为领域状态权威，已有 Redis/Celery 是异步执行载体。

## 数据与运行的权威

Near Agent 可发起研究、读取状态和解释后台结果，但它自己的对话结束不代表领域运行完成。AGX 技术 run/session、Celery result、模型 FinalEvent 都不能替代 ResearchRun。正式 Brief 必须由领域账本在验证后原子发布。

证据登记保存来源、许可、可得时点与版本。`published_at` 与系统首次取得该版本的 `available_at` 不同，固定 `as_of` 查询只读已登记版本，不在查询中 live refresh。冻结快照后不能追加新的资料；新资料需要新 run 和新 request_id。

事实主张必须引用同一 run 快照的证据。市场数字采用十进制字符串、单位和币种；随机行情、测试 fixture、旧分析文字、向量 payload 不成为生产证据。模型只能生成候选与受约束审阅，确定性权限/时间/许可/数值检查不能被模型推翻。

## 新旧规划关系

2026-10-01 的 F01/F02/F03 保留为历史设计参考，不继续按原编号直接派实施。新 Master 将顺序收敛为：

`S00 兼容/契约 → S01 最小后台装配 → S02 权限/证据/账本 → S03 公共读服务与 MCP + S04 可靠 worker → S05 AGX 研究 Flow + S06 Near 扩展 → S07 集成门禁`。

旧 AGX 配套规划 PR #65 仍需单独修订与处理，不自动合并。A01 的通用 façade/事件框架不再是首期无条件前置；A02 的金融 HTTP/SSE Electron bridge 和 A03 的新侧栏移为后置候选。只有测试证明现有底座缺具体能力，才开启 G01 通用小补丁。

研究进程崩溃首期采用保守策略：至少一次投递，数据库 claim/fence 与唯一产物发布；lease 到期收口为 failed，修复后新 run 重试。不声称外部模型费用 exactly-once，不自动扩展失败 run 的时间快照。

## 当前交付与后续依赖

S00 已交付精确 SDK pin/lock、实际 Flow/ReAct 调用测试、research-v1.1 Pydantic DTO/Schema/fixture 和兼容报告。已选 PyPI `agenticx[mcp]==0.6.5`，MCP 1.30.0；31 项测试、全 S00 Python Ruff 和 pip check 通过，并完成审查问题修复与独立复审。这些不等于生产鉴权、数据库迁移、MCP endpoint 或实际金融研究已完成。

[兼容报告](../compatibility/agx-research-baseline.md) 和 [C1 契约](../contracts/research-v1.1/README.md) 已提供可复跑输入；C1 本地冻结 digest 为 `591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e`。JSON Schema 只能证明结构和格式，服务端 principal 授权、来源政策、快照成员与数值复算分别由 S02–S05 强制执行。

后续待输入：身份签发方/公钥与服务地址、第一条事件来源许可、可选市场来源、批准模型与试点预算。缺这些输入不阻断离线 fixture 开发，但不能启用真实研究或宣称已经接入合法金融数据。

## 两仓与本地工作保护

本轮 FNH 隔离实现分支为 `feat/finnews-agent-first-wave-1`，基线 `89c50de283d87de07c358b39e8d9e1e1b59eeb55`；AGX 执行索引基线 `ebe368530fb478b8fbfc02e6316da5cbccef1a19`。SDK 发布标签与当前 main 不同，实际选择以兼容报告为准，不能用 distribution version 替代源码 SHA。

用户原工作树的 requirements、文档和子模块指针不作为本波实现载体。所有研究模型/迁移与旧表隔离，真实数据不由清库或旧 create_all 初始化。没有用户授权不得 push/merge/生产部署，也不得为测试执行删除数据或下单操作。
