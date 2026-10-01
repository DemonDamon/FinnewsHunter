# F03｜证据化研究 Flow、金融模型路由与评测

Planned-with: Manus
Suggested-Impl-Model: **强推理代码模型 + 金融数据/安全 Reviewer**；本项须同时处理跨服务契约、时间可得性、确定性数值复算、模型回退和离线门禁，实施模型应擅长异步 Python、Pydantic/pytest 与失败路径设计，Reviewer 应复核金融口径、许可与拒答行为。
Parent-Plan: [`2026-10-01-finance-agent-master.plan.md`](2026-10-01-finance-agent-master.plan.md)（C0 冻结契约、第 3–8 节 DAG/边界/合流规则）
Plan-Id: `2026-10-01-finance-F03-research-model-eval`
Plan-Type: `Implementation Subplan / Pending`
状态: **待用户确认；本文件不是实现完成声明。**

> **实施前置**：仅在 F01、F02 与 A01 均已合并、F01 的 `ResearchRunDispatcherPort`/typed Port 与 F02 的 contract manifest fixtures 可用且 C0 未发生未同步变更后开始。F01/F02 **计划已存在**；实施时以它们合并 PR 所发布的 exact module path、`port_version`、task name 和 manifest digest 为准，不能猜测未合并实现的类名或行为，也不能另造兼容层。

## 1. 目标与 1–2 周边界

为**一则已选定的 A 股事件 + 一个股票实体**建立受限、可审计的研究 run：从 F02 提供的合规证据和行情快照出发，以 AgenticX `Flow` 固化步骤、以受限 `ReActAgent` 仅调用 F02/A01 允许的只读工具，产出符合 C0 的 `ResearchBriefV1`。每一条事实性 `ClaimV1` 必须能回指同一快照内的 `EvidenceV1`，并通过引用审阅和确定性数值校验；无法满足时进入 `needs_review` 或作为显式未知项，而不是生成无证据结论。

同时增加**任务级模型路由与离线评测门禁**：领域候选模型只有在版本化离线用例达到明确门槛后才可被配置为可选路由目标；否则只使用已批准的通用回退模型，或拒答/转人工复核。该工作是运行时选择、审计和评测，不包含微调、训练、模型发布或“金融模型已训练完成”的任何主张。

时间盒为 **1–2 周**，仅实现下列单事件、单股票、只读场景；不扩展为通用研究平台。

## 2. 基线、根因与代码证据

| 观察 | 代码/计划锚点 | 对 F03 的影响 |
|---|---|---|
| C0 已冻结 `EvidenceV1`、`ClaimV1`、`ResearchRunV1`、`RunEventV1`、`ResearchBriefV1` 及 `/api/v1/research/*` 语义；并要求 `available_at <= as_of`、无许可不返回全文、数值不一致不得作为事实。 | master 第 24–39 行；第 90–96 行 | F03 只消费这些对象，不能重新定义 schema、状态机、鉴权或 SSE 语义。 |
| 当前 `DebateOrchestrator.run()` 接受自由文本 `context/news_list`，将过程事件放在实例内存的 `self.events`，并执行多空辩论/最终评级。 | `backend/app/agents/orchestrator.py:64-105,140-198,200-294` | 现有辩论轨迹不能充当持久化 `ResearchRunV1` 或证据账本；F03 需新增独立研究 Flow，不能把 `DebateEvent` 直接冒充 C0 事件。 |
| Bull/Bear/Manager 的输入输出主要是自然语言，Manager 提示词还包含“买入/卖出/加仓/清仓”操作建议。 | `backend/app/agents/debate_agents.py:26-164,351-509`，尤其 `401-462` | F03 只新增受约束的引用审阅角色，不复用/暴露该投资操作建议路径，也不把原辩论文本视为已核证主张。 |
| `NewsAnalystAgent.analyze_news()` 直接把新闻标题/正文交给模型，并要求 Markdown 报告；现有提取依赖正则。 | `backend/app/agents/news_analyst.py:89-262,325-418` | 需增加只接受已许可 Evidence 投影的结构化候选主张生成入口；不能从自由 Markdown 推导事实或数字。 |
| LLM 服务可由调用方指定 provider/model；`create_custom_llm_provider()` 对不支持项回退默认 provider，但没有按任务的批准状态、评测版本或审计 trace 路由。 | `backend/app/services/llm_service.py:260-284,300-430`；`backend/app/core/config.py:75-127` | F03 增加受 allowlist 与离线评测门禁约束的研究任务路由，禁止请求直接选择未评测模型。 |
| 金融工具已有 `FinancialNewsTool`、`StockPriceTool` 和按优先级 Provider Registry，但其返回尚不是 C0 证据/时间/许可包装。 | `backend/app/financial/tools.py:28-136,139-251`；`backend/app/financial/registry.py:129-182` | F03 不绕过 F02 直连这些工具；只经 F02 已封装的 HTTP/MCP/领域服务读取证据和行情口径。 |
| `alpha_mining` 显式导入并多处调用 `generate_mock_data()` 执行训练、生成和评估。 | `backend/app/api/v1/alpha_mining.py:144-170,179-246,284-402,405-477,480-638` | 研究 run 不得导入、调用或呈现 Alpha Mining 模拟数据、因子得分或训练进度；该实验路径必须保持隔离。 |
| AgenticX 当前 checkout 提供异步函数调用 `ReActAgent.astream/arun()` 与 `Flow.kickoff_async()`；Flow 可承载 `@start/@listen/@router` 步骤。 | `AgenticX/agenticx/agents/react_agent_async.py:98-155,581-814`；`AgenticX/agenticx/flow/__init__.py:15-41`、`flow/base.py:254-372` | F03 可消费 A01 对应版本的通用原语，但不在 `FinnewsHunter/AgenticX/` 修改 Runtime，也不引入第二个编排引擎。 |
| 部署依赖目前固定 `agenticx==0.1.9`，而本地嵌套 checkout 的能力可能与该包版本不同。 | `backend/requirements.txt:47-49` | 实现的首个门禁必须验证 A01 实际发布/锁定版本的 Flow、ReAct 与安全远程 MCP 支持；不通过则停止而非复制 Runtime。 |

## 3. 冻结契约与设计约束（不得放宽）

1. **权威边界**：F01 的持久化 `ResearchRunV1`、事件账本、principal 授权和幂等规则保持权威；F02 的 HTTP/MCP、证据、行情口径、权限与 fixtures 保持权威。F03 在**自己新增的 worker module**实际注册并消费 F01 dispatch task，再调用执行器/适配器；不新建平行的数据库、SSE、认证或业务状态机，也不编辑 F01/F02 shared modules。
2. **C0 数据不变量**：流中仅将 `quality_status` 合格、许可允许的 `EvidenceV1` 投影提供给模型；每个被采用的证据均满足 `available_at <= run.as_of`，并保留 `evidence_id`、`content_hash`、来源与时间。受 `no-redisplay` 等许可限制的内容不进入提示词、事件 payload、日志或 Brief 全文，只保留 C0 允许的最少来源元数据。
3. **主张不变量**：`kind=fact` 必有一个或多个同快照 `evidence_ids`；`inference`、`hypothesis` 显式标识并列入限制/未知项；未能引用、矛盾或数值校验失败的内容不能升级为事实。
4. **工具最小化**：ReAct 仅可访问 F02/MCP v1 已允许的 `finnews.search_articles`、`finnews.get_evidence`、`finnews.get_market_snapshot`，以及由 F02 暴露的该 run 受权范围内数据；不开放任意 URL、SQL、文件系统、付费内容、交易、券商或 Alpha Mining 工具。A01 的统一 principal、TLS 和 fail-closed 行为必须贯穿这些调用。
5. **事件与可观测性**：Flow/ReAct 的步骤与工具结果映射到 F01 的 `RunEventV1`（严格递增 `seq`），包括 `started`、`step_started`、`evidence_added`、`claim_checked`、`needs_review`、`completed`/`failed`。禁止使用 `DebateOrchestrator.events`、`api/v1/agents.py` 的内存 `execution_logs/debate_results` 作为权威记录。
6. **非交易研究**：Brief 只给出有证据的事实、显式推断、反方论据、未知项、限制及模型 trace；不输出交易指令、收益承诺、价格预测或 Alpha 模拟绩效。

## 4. 范围

### In scope

- 单事件、单股票的异步 `EventStockResearchFlow`；输入为 F01 创建的 run 与 F02 已冻结的证据/行情快照，输出为 C0 `ResearchBriefV1` 和事件账本更新。
- 在 F03 自己新增的 worker module 中消费 F01 durable outbox 投递的 `finnews.research.execute_run.v1`；以 F01 capability claim queued run 后实际启动该 Flow，使创建 queued run 的正常路径可执行而不是永久排队。
- 受限 ReAct 的工具调用审计、证据投影、候选主张生成、引用审阅、确定性数值校验和失败降级。
- 基于任务/角色（候选主张、引用审阅、摘要）的模型策略：批准记录、显式回退链、`model_trace`、无批准模型时拒答/待复核。
- 版本化、离线、无网络密钥的评测 fixture：工具轨迹、引用/时间、数值校验、路由/回退和拒答门禁。
- Alpha Mining 隔离回归测试。

### Out of scope

- 修改 C0 字段、F01 迁移/状态机/授权/dispatcher、F02 路由/MCP schema/Provider 实现，或新增研究 API 路径；这些属于上游节点。F03 只在已合并 typed Port、fixed task-name 和 manifest 接口上接线。
- 改造现有 `/api/v1/agents/debate`、`/debate/stream`、内存日志或既有 Bull/Bear 投资建议为研究 run；保持其遗留行为与 F03 隔离。
- 通用多股票、多事件、持续跟踪研究，自动下单/券商权限、持仓读取、公开研报分发、付费新闻采购或任意网页抓取。
- 模型微调、训练、权重托管、真实收益/回测证明或“金融垂类模型已完成”声明。
- Near/UI 工作台（A03）和 AgenticX Core/Runtime 改造（A01 所有权）。

## 5. 文件边界

### 预计新增或修改（均为实施时；当前不创建代码）

| 路径 | 动作 | 责任与目的 |
|---|---|---|
| `backend/app/agents/event_stock_research_flow.py` | 新增 | 定义 F03 私有的 `EventStockResearchFlow` 及其状态投影；以 AgenticX `Flow` 组织加载、受限 ReAct、审阅、校验、发布/待复核步骤。它通过注入的 F01/F02 adapter 工作，不复制上游 model。 |
| `backend/app/workers/__init__.py`、`backend/app/workers/research_flow_worker.py` | 新增 | F03 所有的实际 task consumer：注册 F01 固定 task name `finnews.research.execute_run.v1`，验证 delivery/correlation version 后从 F01 `ResearchRunServicePort` 取得内部 `ResearchWorkerCapability` 并原子 claim queued run，再调用 `EventStockResearchFlow`。这是部署 worker entrypoint，不编辑 F01/F02 router/service；重复/过期 delivery 必须 no-op。 |
| `backend/app/agents/orchestrator.py` | 修改 | 在保留 `DebateOrchestrator` 及 `create_orchestrator()` 原语的前提下，添加研究 Flow 的工厂/worker 入口；入口只接收已授权的 run context，不接受任意 `provider/model/context`。 |
| `backend/app/agents/debate_agents.py` | 修改 | 新增仅供 F03 调用的 `CitationReviewerAgent`（或等价明确命名角色）；不改变既有 Bull/Bear/Manager 的遗留接口和投资建议语义。 |
| `backend/app/agents/news_analyst.py` | 修改 | 为 `NewsAnalystAgent` 增加从许可 Evidence 投影生成**结构化候选 Claim**的入口；保留现有 `analyze_news()` 兼容路径，不把其 Markdown/正则结果当作 F03 事实来源。 |
| `backend/app/agents/__init__.py` | 修改 | 导出新 Flow 工厂与研究入口，避免 API/worker 直接导入内部实现。 |
| `backend/app/services/llm_service.py` | 修改 | 在保持通用 `get_llm_provider()` 兼容的同时，提供研究任务专用 `ResearchModelRouter`（或等价明确命名组件），负责批准选择、回退、不可用决策与不可篡改的 trace 输入。 |
| `backend/app/services/research_validation.py` | 新增 | 放置纯函数、无 LLM 的引用结构校验与 `Decimal` 数值/币种/单位/时间确定性校验，便于独立测试。 |
| `backend/app/services/research_evaluation.py` | 新增 | 加载版本化离线评测集、聚合 AgenticX `EvalSet`/`EvalRunner` 的工具轨迹结果与本地引用/数值 gate，生成供配置引用的批准记录；不训练模型。 |
| `backend/app/core/config.py` | 修改 | 增加默认关闭的研究功能开关、允许的模型 profile、评测集版本/报告指纹、阈值和显式通用回退配置；密钥仍只从现有 settings 读取。 |
| `backend/requirements.txt` | 修改（F03 owns this line after F01 merges） | 将当前 `agenticx==0.1.9` 替换为 A01/F03 兼容测试通过的**精确**发布版本或 PEP-508 full-40-character commit pin；记录 release tag + commit SHA，不接受范围、浮动分支、本地 checkout 或“先保持 0.1.9”。该变更是 F03 PR 的 requirements-file ownership。 |
| `backend/tests/research/fixtures/agenticx_compatibility_v1.json`、`test_agenticx_compatibility_lock.py` | 新增 | 记录精确 distribution version、release/commit、Python/FastAPI/MCP 组合、测试日期与 capability expectations；在干净环境安装 requirements 后验证 pin 与 Flow/ReAct/安全 MCP 能力，再允许 F03 代码运行。 |
| `backend/tests/research/test_event_stock_research_flow.py` | 新增 | Flow 的正常、时间倒挂、许可限制、事件序列与 Brief 契约单测。 |
| `backend/tests/research/test_research_dispatch_worker.py` | 新增 | 使用 F01 fake/测试 outbox transport 验证一次 newly-created queued run 投递到 F03 的 exact task name 后被 claim 并实际启动 Flow；重复 delivery、取消/终态 run、错误 delivery version、Port claim 失败和 Flow 异常都不产生第二次执行或错误的 `completed`。 |
| `backend/tests/research/test_research_claim_validation.py` | 新增 | 引用审阅结果及数值/单位/币种/可得时间的确定性校验单测。 |
| `backend/tests/research/test_research_model_router.py` | 新增 | 批准门禁、候选模型不可用、通用回退与拒答 trace 单测。 |
| `backend/tests/research/test_research_eval_gate.py` | 新增 | 小型离线评测集和门禁聚合测试，不调用真实模型/Provider。 |
| `backend/tests/research/test_alpha_mining_isolation.py` | 新增 | 防止 F03 研究模块及路由策略引用 `app.alpha_mining` 或 `generate_mock_data` 的回归测试。 |
| `backend/tests/research/fixtures/event_stock_research_v1.json` | 新增 | 去敏、许可可再分发的固定 Evidence/行情/期望轨迹 fixture；包含正常、时间倒挂、许可受限、数字不一致和模型不可用情形。 |

### 明确不得修改

| 路径/边界 | 原因 |
|---|---|
| `backend/app/api/v1/alpha_mining.py` 与 `backend/app/alpha_mining/**` | 其中的 `generate_mock_data()`/训练/因子实验不是事实行情或研究证据，F03 不得连接、包装或改变其输出。 |
| `backend/app/api/v1/agents.py` | 当前辩论 API 使用内存 `execution_logs`/`debate_results`，且输出非 C0 研究契约；F03 不以隐式替换方式改变该遗留端点。 |
| F01 所有 `ResearchRun`、Evidence/Claim 持久化模型、迁移、授权和 event-ledger 文件 | 上游权威所有权；若 F03 所需扩展无法由现有上游接口表达，先修订 C0/上游 PR，不在 F03 影子实现。 |
| F02 已合并的研究 HTTP/MCP 路由、OpenAPI 与 provider/fixture 实现 | 上游权威所有权；本项只消费接口与契约 fixture。 |
| `FinnewsHunter/AgenticX/**` | 它是独立 checkout，F03 只消费 A01 已发布/锁定的 API；禁止嵌套仓改动或父仓提交。 |
| `backend/app/main.py`、`backend/app/api/v1/__init__.py`、F01 `research.py`/`research_dispatch.py` | F03 不新增/重注册 HTTP route，也不修改 F01 shared router/dispatcher；研究 API 挂载权归 F01，F02 只扩展 evidence handler。F03 仅以自己新增的 worker module 附着到 F01 已发布 task contract。 |

## 6. 功能需求与实施意图

### FR-1：以 C0 run 为边界的单事件研究 Flow

**Before**：`DebateOrchestrator.run()` 从自由 `context/news_list` 开始，事件只保存在进程内，并可产生遗留评级；F01 之外没有能够消费 queued research run 的实际 worker。
**After**：F01 创建 run 后由其 durable dispatcher 投递固定任务；F03 新增的 `research_flow_worker` 消费该任务、在已有 `run_id` 上原子 claim 后启动 `EventStockResearchFlow`。它只接受一个事件、一个实体和已鉴权的 run snapshot；Flow 通过 F01 Port 报告状态/事件，绝不自行创建第二个 run 或第二份状态机，也不要求修改 F01/F02 router/service。

**意图伪代码（非实现）**：

```text
F03 task finnews.research.execute_run.v1(run_id, dispatch_id, port_version):
  capability = f01_dispatch_delivery.verify(dispatch_id, port_version)
  run = f01_run_port.claim_queued_run_for_execution(capability, run_id)
  if run is None: return no_op  # duplicate delivery, cancelled, or terminal
  require run.status == running and len(run.entity_ids) == 1
  emit RunEventV1.started / step_started via f01_run_port
  return run

listen(load_authorized_run -> materialize_snapshot):
  evidence, market = f02_gateway.get_run_scoped_inputs(run_id, as_of)
  allowed = filter(evidence, quality_ok && available_at <= as_of && license_allows_projection)
  record excluded ids + reason without restricted body
  return allowed, market

router(materialize_snapshot):
  return "RESEARCH" when minimum evidence/market policy is met
  return "NEEDS_REVIEW" otherwise
```

- `Flow.kickoff_async()` 用于 FastAPI/Celery 的异步上下文；不在运行中的 event loop 调用同步 `kickoff()`。
- 研究 Flow 的本地 `flow_id` 只作技术关联，`ResearchRunV1.run_id` 始终是业务主键。worker claim 后可在 `running` 的证据收集阶段通过 F01 Port 逐条 `attach_evidence_before_freeze` 并发出 `evidence_added`；首条 Claim 写入前必须 `freeze_snapshot`，冻结后新搜到的 Evidence 不得加入本次 run，须创建新 run。
- worker 启动命令/queue binding 必须加载 `app.workers.research_flow_worker` 并订阅 F01 dispatcher 的 research queue；部署验收以一次 F01 新建 run 的 outbox delivery 驱动该 task，而不是手工直接调用 Flow。数据不足、F02/A01 断连、授权失败、run 已取消或写事件失败时，停止执行并由 F01 状态机登记 `needs_review`、`failed` 或 `cancelled`；绝不写 `completed`。worker 崩溃或 delivery 重试时只能经 `claim_queued_run_for_execution` 去重，不能二次生成 Brief/事件序列。

### FR-2：受限 ReAct 证据收集与可重放的过程映射

**Before**：现有动态搜索从辩论文本解析 `[SEARCH: ...]`，可把补充摘要直接拼回 prompt。
**After**：研究 Flow 使用 A01 提供的安全远程 MCP 适配和 AgenticX `ReActAgent.astream()`，工具 allowlist 固定为 C0/F02 的只读工具；所有 ReAct typed event 转换为 F01 持久化的 `RunEventV1`，并把工具返回先规范成 C0 证据/行情投影后才进入模型上下文。

**意图伪代码（非实现）**：

```text
react = ReActAgent(
  llm=model_router.select(role="claim_draft", run=run),
  tools=f02_gateway.allowed_tools(run, names={search_articles, get_evidence, get_market_snapshot}),
  model_name=model_trace.model_id,
  max_iterations=policy.max_react_iterations,
)
for event in react.astream(evidence_bounded_question):
  map Reasoning/ToolCall/ToolResult/Final/Error to sanitized RunEventV1 payload
  append_event_strictly(run_id, next_seq, event)
  reject tool result if evidence_id, available_at, license_scope, currency/unit/timezone metadata are absent
```

- 搜索只能补入同一 run、同一 principal、同一 `as_of` 可见范围的证据；不得把模型请求直接翻译为任意 URL 或 Provider 调用。
- 日志、trace 与提示词只保留允许重展示的 excerpt；对于限制许可来源，记录来源标识/许可状态和拒绝原因，不写原文。
- 无法确认 A01 所用 AgenticX 版本同时具备受限工具、typed event 和远程身份传播能力时，停止 F03；不复制 Runtime、也不退回 `SearchAnalystAgent` 的自由文本标记方案。

### FR-3：证据绑定的候选 Claim 与引用审阅

**Before**：`NewsAnalystAgent` 和现有辩论角色主要输出 Markdown/自然语言，引用没有机器可校验的 `evidence_ids`。
**After**：`NewsAnalystAgent` 的 F03 入口只接收经过 FR-1 投影的 `EvidenceV1`，产生 Pydantic 可解析的候选项；新增 `CitationReviewerAgent` 对“主张—证据片段—时间—许可”逐条标记 `supported`、`insufficient` 或 `conflicting`。Reviewer 不能新增来源、数字或投资操作建议。

**意图伪代码（非实现）**：

```text
candidates = news_analyst.draft_claim_candidates(allowed_evidence, as_of)
for candidate in candidates:
  structural = validate_claim_shape(candidate, evidence_by_id, as_of)
  review = citation_reviewer.review(candidate, cited_evidence_projection) if structural.ok else insufficient
  if candidate.kind == "fact" and (not structural.ok or review != "supported"):
      move_to_unknowns_or_needs_review(candidate, reason)
  else:
      retain_with_explicit_kind_and_confidence(candidate)
```

- 结构校验先于 LLM reviewer：事实没有 citation、引用不属于当前快照、`available_at > as_of`、受限正文泄露、或 `valid_until` 已失效，均不可进入 reviewer 通过分支。
- 保留看多/看空的反方论据只能作为 `counterarguments`，也必须带证据或显式“不足/未知”标识；不复用 `InvestmentManagerAgent.make_decision()` 的评级/操作字段。
- 最终 Brief 包含 `claims[]`、`counterarguments[]`、`unknowns[]`、`limitations[]` 和 `model_trace`；不能以“情绪分数”代替行情事实或价格判断。

### FR-4：确定性数值、单位和时点验证

**Before**：当前新闻结构化提取以正则提取评分/文本，模型生成的涨跌幅、金额和单位没有独立复算。
**After**：`research_validation.py` 为每个带数值的事实 Claim 建立可追溯的数值断言（`evidence_id`、字段、原始值、标准化数值、币种、单位、市场时区/复权说明）；仅以 F02 行情/公告规范字段和 Python `Decimal` 复算，LLM 不参与最终判定。

**意图伪代码（非实现）**：

```text
for assertion in claim.numeric_assertions:
  source = snapshot.lookup(assertion.evidence_id, assertion.field)
  expected = decimal_recompute(source, market_convention, as_of)
  if units_currency_timezone_or_value_mismatch(assertion, expected):
      reject_fact(claim, error_code="numeric_validation_failed")
      emit claim_checked(status="rejected", provenance=source.id)
```

- 覆盖至少：价格/涨跌幅、金额/数量级、百分比与百分点、币种、复权、市场时区、分母为零与缺失值。
- 校验器**不静默篡改**模型叙述；数值不一致时拒绝其事实身份，放入 `unknowns`/`limitations` 或 `needs_review`，并留下可审计错误码。任何“纠正”只能由带可追溯源字段的确定性渲染器重新生成，而非模型猜测。
- 没有可复算来源的数字不得成为 `fact`，即使 reviewer 语言上认为合理。

### FR-5：领域模型路由、离线评测门禁与回退

**Before**：调用方可以经 `get_llm_provider(provider, model)` 选择模型；`create_custom_llm_provider()` 在部分异常下回落默认模型，缺乏任务批准状态、评测报告和可审计决策。
**After**：研究 Flow 通过专用 router 按角色选择 profile。profile 至少包含 `model_id`、provider、用途、允许工具能力、评测集版本/报告指纹、阈值、批准状态、回退 profile 和提示词版本。仅 `approved=true` 且本地评测记录满足阈值的 profile 可路由；候选金融模型默认不可用，绝不因名称或配置存在而视为已训练/已通过。

**意图伪代码（非实现）**：

```text
primary = policy.approved_profile(role, evalset_version, report_digest)
if primary and provider_health(primary):
  return primary, trace(selection="approved_primary")

fallback = policy.approved_general_fallback(role)
if fallback and provider_health(fallback):
  return fallback, trace(selection="approved_fallback", cause=primary_failure)

return no_model, trace(selection="refuse", cause="no_approved_model")
```

- 评测集用去敏、许可可分发的离线 fixtures，版本化存放；使用 AgenticX `EvalSet`/`EvalRunner` 检查期望工具轨迹，并叠加 FR-3/FR-4 的确定性引用、时间和数值 gate。通过的必要条件至少包括：无越权工具调用、所有事实引用完整、无时间倒挂、数值零误差/规定舍入误差、回退/拒答路径正确；阈值由配置显式记录，不在代码中暗含“模型表现好”。
- 每次 run 在 `model_trace` 写入实际 `model_id`、角色、prompt_version、policy_version、评测集版本/报告摘要、选择原因、回退链和工具轨迹摘要；不得记录密钥、受限全文或未脱敏 prompt。
- 评测 runner、批准报告和运行时路由是不同阶段：离线评测不会自动激活 profile；需要人工/配置批准后才可启用。评测失败、报告缺失、provider 健康检查失败或配置不一致均降级到已批准通用模型，或 `needs_review`/拒答。

### FR-6：以兼容性测试过的发布物/commit 升级并锁定 AgenticX

**Before**：`backend/requirements.txt` 固定 `agenticx==0.1.9`，而 F03 所需的 `Flow.kickoff_async()`、async `ReActAgent`、typed event 与 A01 安全远程 MCP 能力没有被该 pin 证明；仅在运行时“遇到不兼容就停止”会让 queued run 永远不可执行。

**After**：F03 PR 负责消费 A01 已发布的兼容构建，并实际替换 0.1.9 pin。选择流程是：A01 提供候选 published release tag 与不可变 40-character source commit（或仅提供经过发布验证的 full commit）；F03 在干净环境对该候选运行本计划的 worker/Flow/MCP security compatibility suite；通过后，F03 **在 `backend/requirements.txt` 中拥有并提交**精确 pin（exact release，或 PEP-508 VCS URL 的 full commit），同时在 `agenticx_compatibility_v1.json` 记录 distribution version、release tag、commit、resolver output digest 与测试报告 digest。不得保留 `agenticx==0.1.9`、范围运算符、branch 名、未锁定本地 editable checkout 或“以后再升级”的说明。

- 兼容性门禁至少覆盖：干净环境 `pip install -r requirements.txt`/`pip check`；导入并执行实际 pin 的 `Flow`、`ReActAgent.astream()`、`kickoff_async()`；F01 fixed-task delivery 到 F03 worker 的 claim/no-op 重投递；A01 的 audience-bound remote MCP principal 传递与拒绝 desktop token；F02 manifest 的 required `as_of`/`run_id` 失败路径。测试结果、Python/FastAPI/MCP SDK resolved versions 和 release/commit 必须与 fixture 匹配。
- 安装或 capability 测试失败时，该候选不进入 requirements，F03 选择下一个 A01 release/commit 并重复测试；一旦通过即以 exact pin 合并，并以 default-off `RESEARCH_FLOW_ENABLED` 分阶段启用。这是有闭环的升级/锁定工作，不是无限期停在 0.1.9 或复制嵌套 AgenticX Runtime。
- 后续升级必须新建 compatibility fixture/report、修改 exact pin 并重新跑完整 suite；运行时不得静默回退到不同 AgenticX 版本。

## 7. 实施顺序

1. **前置核验（停止点）**：确认 F01/F02/A01 已合并，读取 F01 actual `research_ports.py`、dispatcher task contract/queue binding、F02 manifest/adapter、权限和事件 writer 路径；按照 FR-6 选择候选 AgenticX release/commit，完成测试后在本 PR 更新并锁定 `backend/requirements.txt`。若任一项不成立，记录可行动的阻塞（缺哪个 release/Port/fixture），不启动 worker/Flow。
2. **先测后码**：先建立 `backend/tests/research/fixtures/event_stock_research_v1.json` 与 FR-1–FR-5 的红灯测试；全部使用 fake F01/F02 gateway 和 scripted LLM，禁止真实 Provider/网络/数据库依赖。
3. **纯确定性层**：实现引用结构、时间/许可过滤和数值校验，再实现候选 Claim 与 CitationReviewer 的适配；先保证失败内容无法发布为事实。
4. **worker、Flow 与 ReAct 接线**：在 F03 新 worker module 注册 F01 exact task name，验证 delivery、claim queued run、run-scoped adapter 注入、事件映射、ReAct allowlist 与 Brief 组装；由 F01 outbox 真实投递触发，不修改 API contract、F01 dispatcher 或 F02 router。
5. **模型 router 与 eval gate**：以 default-off 配置上线 profile 选择、trace、离线评测/批准记录及回退；候选领域模型保持 disabled，直到明确评测与人工批准。
6. **回归与审查**：运行本计划的离线测试、F02 契约 fixture 回归及 Alpha 隔离检查；安全/金融 Reviewer 复核许可证、`available_at`、单位/币种/复权和拒答行为。

## 8. 可执行验收测试

所有测试均应在实现分支中新增，使用 fixtures/fake adapter/scripted LLM；**不得**配置真实模型密钥、真实交易、真实训练或网络 Provider。下列命令是实施完成时的验收命令，不表示当前工作树已经通过。

| 测试文件 | 断言 |
|---|---|
| `backend/tests/research/test_agenticx_compatibility_lock.py` | 在全新 venv 从已修改的 `requirements.txt` 安装后，断言 distribution version、release/40-char commit 与 `agenticx_compatibility_v1.json` 相同且不等于遗留 0.1.9；`pip check` 通过，实际 `Flow.kickoff_async()`、`ReActAgent.astream()`、A01 安全 MCP principal/desktop-token 拒绝路径可用。任何 fixture/installed package/resolver digest 偏差失败。 |
| `backend/tests/research/test_research_dispatch_worker.py` | 通过 F01 test outbox transport 创建一次 queued run，断言 emitted task name/contract version 为 `finnews.research.execute_run.v1`，F03 worker claim 后调用 `EventStockResearchFlow` 并写正确的 started/terminal 或 needs_review 事件。重投递、取消/已终态、delivery version 不匹配、capability claim 失败、Flow 异常都不二次执行、不重置 seq、不写伪 `completed`；测试不手工直调 Flow 作为 dispatch 替代。 |
| `backend/tests/research/test_event_stock_research_flow.py` | 用一个合规、可展示、`available_at <= as_of` 的事件 fixture 执行 `EventStockResearchFlow.kickoff_async()`：断言结果引用同一 `run_id`、每个 `fact` 至少一个当前快照 `evidence_id`、Brief 含 `as_of/model_trace/limitations`，持久化事件按 `seq` 严格递增且含 `started → step_started → evidence_added → claim_checked → completed`。再用 `available_at > as_of` fixture：断言该证据未进入事实、run 为 `needs_review`（或上游规定的失败状态）且事件 payload 仅记录拒绝理由。再用 `no-redisplay` fixture：断言受限正文不出现在 Brief/事件。 |
| `backend/tests/research/test_research_claim_validation.py` | 断言无 `evidence_ids` 的 `fact`、跨快照引用、冲突引用和许可受限正文均被拒绝；对可复算价格 10→11 的 10% 主张通过，15% 主张失败；金额 `1.2 亿元` 与 `1.2 百万元`、百分点与百分比、币种/时区/复权缺失、零分母均失败并生成明确错误码；校验器不改写模型文本。 |
| `backend/tests/research/test_research_model_router.py` | 对未经批准或评测版本/报告摘要不匹配的领域 profile，断言 router 不实例化它；首选 provider 异常时只选择已批准通用 fallback，`model_trace` 记录原因；无批准 fallback 时断言不调用 LLM 且 Flow 进入 `needs_review`/拒答，绝不偷偷使用 settings 默认模型。 |
| `backend/tests/research/test_research_eval_gate.py` | 以固定 EvalSet/fixture 驱动 scripted ReAct：合法只读工具轨迹和全部确定性 gates 通过；任意 URL/不在 allowlist 的工具、时间倒挂、数值不一致或缺少 citation 的 case 失败；失败的报告不能令 profile 变为 approved。 |
| `backend/tests/research/test_alpha_mining_isolation.py` | 静态检查 F03 新研究模块、worker、router 与 fixture 中没有 `app.alpha_mining`、`generate_mock_data`、`AlphaMiningTool` 或 `/alpha-mining` 引用；导入研究模块/worker 不触发训练/Mock 数据生成。 |

```bash
cd /home/ubuntu/FinnewsHunter/backend
PYTHONPATH=. pytest -q \
  tests/research/test_agenticx_compatibility_lock.py \
  tests/research/test_research_dispatch_worker.py \
  tests/research/test_event_stock_research_flow.py \
  tests/research/test_research_claim_validation.py \
  tests/research/test_research_model_router.py \
  tests/research/test_research_eval_gate.py \
  tests/research/test_alpha_mining_isolation.py

# F01/F02 合并后，以 F02 manifest discovery 运行，不得复制一份冲突协议或跳过 replay/error fixtures。
PYTHONPATH=. pytest -q tests/financial/test_f02_contract_fixtures.py tests/financial/test_f02_mcp.py

# F03 已提交的 exact AgenticX pin 的运行时能力门禁（与 F03 tests 同一环境）。
python -m pip check
python -c "from importlib.metadata import version; from agenticx.agents import ReActAgent; from agenticx.flow import Flow; print(version('agenticx'), ReActAgent.__name__, Flow.__name__)"

# 防止 F03 源码误连 Alpha Mining；预期无匹配输出。
! rg -n 'app\.alpha_mining|generate_mock_data|AlphaMiningTool|/alpha-mining' \
  app/agents/event_stock_research_flow.py app/workers/research_flow_worker.py app/services/research_validation.py \
  app/services/research_evaluation.py app/services/llm_service.py
```

补充人工验收：在隔离环境以 F02 manifest 提供的一条许可合规 A 股事件 fixture**经 F01 POST 创建 queued run**，观察 F01 outbox 被 F03 worker 消费，断线后使用同一 `request_id`/`run_id` 查询 F01 事件账本，确认事实可回指 evidence、数字可复算、`model_trace` 显示实际回退或批准选择；再重投递同一 dispatch 验证 no-op。不得以直接函数调用、Alpha mock 或模拟收益充当验收。

## 9. 失败处理与回滚

| 失败/风险触发 | 行为 | 回滚/恢复 |
|---|---|---|
| F01 dispatcher/Port、F02 manifest、A01 身份契约或候选 AgenticX release/commit 不满足前置 | 不启动 worker/Flow；记录缺失的具体 Port/fixture/release，不以本地替代 adapter、手工直调 Flow 或遗留 0.1.9 绕过。 | 先修订/合并上游或选择下一候选 release/commit，完成 FR-6 compatibility suite 后更新 exact requirements pin，再重新执行前置核验。 |
| 证据许可、质量、`available_at`、ticker 或快照一致性失败 | 移除该证据的正文投影，阻止相应事实 Claim，写 `needs_review`/限制项。 | 保留 F01 事件与原始权威证据引用；获得合规、可用的上游数据后以相同 request_id/run 规则重试。 |
| CitationReviewer、JSON 解析、数值验证或事件写入失败 | 不发布 `completed`；转 `needs_review` 或 `failed`，并附稳定错误码和最小安全 payload。 | 修复后从 F01 权威 run/snapshot 重新执行，不从内存 Debate 轨迹恢复。 |
| 首选模型不可用、报告失效或评测未达门槛 | 仅路由到明确批准的通用 fallback；否则拒答/待复核。 | 将 profile 设为 disabled 或默认关闭，保留 trace；不删除历史 run，不自动更换为未评测模型。 |
| 上线后发现 Flow/Router 缺陷 | 用 default-off 的 `RESEARCH_FLOW_ENABLED`（或实际同义配置）停用 F03 dispatch；不影响 F02 只读查询或遗留辩论端点。 | 回滚该功能 PR/配置；F03 不含 DB migration，数据按 F01 权威保留，未完成 run 依上游状态机标记失败/取消。 |
| 误接 Alpha Mining | CI 隔离测试必须阻断合并。 | 移除连接，保持 `alpha_mining.py` 和实验产物原样；任何受影响 run 一律不得标为基于真实行情的完成结果。 |

## 10. 依赖、审查与交付规则

### 依赖

- **F01（必须已合并）**：持久化 Evidence/Claim/ResearchRun、事件账本、principal 授权、snapshot/幂等/状态转移、versioned `EvidenceRepositoryPort`/`ResearchRunServicePort`，以及固定 `finnews.research.execute_run.v1` durable dispatcher/outbox task contract。
- **F02（必须已合并）**：C0 研究 HTTP/MCP、受限只读工具、证据/行情口径、provider failover provenance，以及 A02/A03/F03 可验证的 versioned manifest（包括 replay/error fixture）和最终 adapter 路径。
- **A01（必须已合并）**：通用安全远程 MCP、统一 principal 传递、结构化 run event 的消费适配，以及供 FR-6 测试/锁定的候选发布 release + immutable commit。
- 已书面确认的来源许可、数据质量/市场时区/单位/复权口径；可离线使用的去敏 eval fixture；至少一个经批准的通用 fallback profile。缺失任一项均是停止条件。

### 未来独立分支与 PR

- 先将本文件按 master 规则从 `.cursor/plans/pending/` 移至 `.cursor/plans/`，并从 **FinnewsHunter 最新 `main`** 建立独立分支：`feat/finance-f03-research-model-eval`。
- 发起单一实施 PR 到 `main`，建议标题：`feat(finance): add evidence-bounded research flow and model gate (F03)`。PR 描述必须链接 F02、A01（及所消费 F01）的已合并 PR/commit、C0 版本、实际 AgenticX 版本、验收命令/结果、评测集版本与已知缺口。
- 不在本 PR 提交 `AgenticX/` 嵌套 checkout；提交前验证 `git ls-files --stage AgenticX` 为空，且 staged 文件仅为本计划批准的 FinnewsHunter 实现/测试文件。不得在依赖未合并时复制他人工作目录伪造前置。
- 合并门槛：上述离线测试全绿、F02 合同 fixture 回归、A01 身份/安全验证、金融 Reviewer 对时点/数值/许可确认，以及安全审查对拒答/回退确认。此 PR 通过不等于 I01 完成；I01 仍需等待 A03 后进行跨仓端到端验收。

## 11. 主要风险与未决项

1. **AgenticX 版本漂移**：遗留 `agenticx==0.1.9` 未证明含所需 API；FR-6 要求 F03 选择 A01 候选、实际跑兼容性 suite、提交精确 release/commit pin 和 fixture report。未经该闭环不能合并/启用，不能在 F03 猜测兼容性。
2. **上游实现路径变化**：F01/F02 计划和契约已存在，但其最终 module path/binding 只能由已合并 PR 确定；F03 用 typed Port/task name/manifest 注入而不硬编码内部 ORM symbol。任何 schema 或 task-contract 差异先回到 C0/F01/F02，而不是在 worker 内建立旁路。
3. **模型非确定性**：结构化输出、引用 reviewer 和领域候选模型均可能幻觉；确定性结构/数值 gate 与默认 fail-closed 是主防线，LLM reviewer 不是证据权威。
4. **数据许可与时点缺口**：爬取新闻/Provider 的发布时间不等于可得时间，且受限全文不可进入 prompt/log；缺少 `available_at`、license 或市场口径时只能降级，不能补猜。
5. **离线评测能力边界**：小型 fixture 能证明协议、工具轨迹、引用和数值防线，不能证明投资收益、泛化金融能力或模型训练完成；上线前仍须持续审查许可与模型卡。
