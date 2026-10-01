# F02：无头金融 API、只读 MCP 与多源检索（待实施）

Planned-with: Manus
Suggested-Impl-Model: **代码专精中档** — 本节点主要是 FastAPI/MCP 协议适配、授权一致性、Provider 降级与可重复的契约测试；需要严守金融数据许可、时点和失败闭环，但不涉及 F03 的模型推理/评测。
Parent-Plan: [`2026-10-01-finance-agent-master.plan.md`](./2026-10-01-finance-agent-master.plan.md)
Plan-Id: `2026-10-01-finance-02-headless-mcp`
Plan-Type: Implementation Subplan（**pending，未实施**）
Depends-On: **F01 已合并至 FinnewsHunter `main`**，并已通过其 Evidence/Claim/ResearchRun、统一 principal 授权、持久化 RunEvent 和迁移回归测试。
建议实施窗口: **1–2 周（单一 FinnewsHunter 分支/PR）**

> 本文只描述后续实现，不声称任何接口、MCP 服务、真实数据源许可或降级能力当前已可用。F01 **计划已存在**，并规定会发布 versioned typed `EvidenceRepositoryPort`、`ResearchRunServicePort` 和 dispatch hook；F02 以该已文档化契约为唯一集成面。若 F01 实现合并时偏离该契约，先修订 F01/C0 和本计划，不能在 F02 复制一套身份、Evidence 或 run 状态机。

## 1. 目标与冻结契约

将 FinnewsHunter 暴露为可由远程工作台消费的**无头、受保护、可审计**金融研究边界：HTTP 与 MCP 调用同一领域读服务、同一 principal 授权和同一许可/可用时间过滤；只注册 C0 冻结的五个 MCP 工具；检索结果始终给出可追溯来源、许可状态与降级轨迹。`start_research` 仅创建受限的研究 run，不是交易或券商动作。

本节点必须保持 Master Plan C0 v1 的以下不变量：

| 契约面 | F02 必须保持的行为 |
|---|---|
| HTTP | 最终精确提供 C0 四条路径。**F01 已创建并注册** `research.py` 的 `POST /runs`、`GET /runs/{id}`、`GET /runs/{id}/events`；F02 只能修改/扩展这个 router 以加入 `GET /evidence/{id}`，不得新建模块、重复 include/router 注册或重实现前三条。`request_id + principal` 幂等，跨 principal 不复用。 |
| MCP | 仅 `finnews.search_articles`、`finnews.get_evidence`、`finnews.get_market_snapshot`、`finnews.start_research`、`finnews.get_run`；`search_articles` 必须显式传带时区 `as_of`，`get_evidence` 必须显式传 `run_id`；不得出现 SQL、任意 URL、删除、付费抓取或任何交易工具。 |
| 包装与时点 | 每个 MCP 结果带 `schema_version`、`as_of`、`source` 和许可状态；证据遵守 `available_at <= as_of`，返回的 `EvidenceV1` 保留 C0 的全部字段及带时区 ISO-8601 时间。 |
| 授权与安全 | HTTP/MCP 都交给 F01 的同一 principal/资源范围判定；未认证、越权、远程 MCP 失联或证书异常均 fail closed。`research:create` 是 `start_research` 的额外权限。 |
| 禁止事项 | 无下单、撤单、券商登录、账户/持仓读取、资金权限、收益承诺或将模拟行情包装为真实行情。 |

## 2. 基线、根因与证据

| 已核对位置 | 事实与根因 | 对 F02 的含义 |
|---|---|---|
| `backend/app/financial/providers/base.py:24-45,129-157` | `ProviderInfo` 只有名称、站点、凭证和优先级；`BaseFetcher.fetch()` 一旦异常即抛出，未保存尝试、耗时、许可或可用性。 | 增加来源政策/尝试结果的领域抽象，不能把“按优先级选第一个”称为实际 failover。 |
| `backend/app/financial/registry.py:129-181` | `get_fetcher()` 仅返回第一个支持类型的 Fetcher，执行失败不会继续下一个 Provider。 | 增加受策略约束的执行级 failover（不是只选择 Fetcher）。 |
| `backend/app/financial/tools.py:53-117,162-231` | 两个 AgenticX 工具直接返回 `NewsData`/行情数据，以模块路径猜测 Provider 名称；没有 principal、许可、provenance 或降级链。 | 保留其兼容用途，但让 F02 的 HTTP/MCP 只通过新的公共领域读服务；不得让两个入口各自实现过滤。 |
| `backend/app/api/v1/news_v2.py:25-143` | import 时注册 Provider，`/fetch` 直接回传 `content`；无身份、`available_at`、许可状态或来源尝试记录。 | 此路径须改为安全的公共检索投影/标记废弃；无有效再展示许可时不可返回全文。 |
| `backend/app/storage/vector_storage.py:82-151` | 实际文件是 `storage/vector_storage.py`，不是任务描述中的 `services/vector_storage.py`；payload 仅有 `news_id` 和截断 `text`，相似度结果无 principal、许可、时间或 Evidence 映射。 | 向量命中只能做候选召回；最终必须回查 F01 Evidence/授权/时点，不能把 `text` 当作可展示证据。 |
| `backend/app/knowledge/graph_service.py:371-453` | `get_company_graph()` 与 `get_search_keywords()` 可以只读扩展实体关键词；同一服务还包含 build/update/delete 写路径。 | F02 只调用只读关键词/实体查询，绝不从 MCP/检索路径触发图谱构建、更新或删除。 |
| `backend/app/services/stock_data_service.py:208-274,430-482` | 现有 AkShare 行情服务的 K 线失败可生成 mock 数据；实时行情失败返回 `None`，且当前输出没有许可元数据、市场数据时间、币种/单位/时区。 | 不能直接作为 C0 “真实行情”结果；只有经过来源政策批准、能提供完整口径的适配器才可进入 `get_market_snapshot`，否则明确 `data_unavailable`。 |
| `backend/app/financial/providers/sina/provider.py:19-34`、`tencent/provider.py:18-33` | 当前默认 Provider 只声明 `news`；未声明许可策略，尚无 `stock_price` Fetcher。 | 不伪称已有行情多源能力；真实新闻 Provider 的运行级降级先落地，行情由批准后的 Provider 才启用。 |
| `backend/requirements.txt:1-51`、`backend/app/**` | 后端没有 MCP server 模块/依赖；嵌套 `AgenticX/agenticx/tools/remote_v2.py:85-154` 的消费者可配置 `streamable_http`/SSE/stdio 和授权 headers。 | FinnewsHunter 需显式引入兼容的官方 `mcp` SDK 并提供服务端；优先远程 HTTPS streamable HTTP，以 AgenticX 已支持的 headers 传递金融服务凭据。 |

本目录现已包含 F01 计划；F02 不应再声称 F01 缺失。实现开始仍须以 F01 合并 PR 所发布的 `research_ports.py` 的 module path、`port_version` 和 composition-root binding 为准，并对其契约进行编译/fixture 验证，而不是猜测或另造兼容层。

## 3. 范围

### In scope

- 在 F01 公共服务之上实现 **一个** `FinancialReadService` 及 typed request/response/provenance 政策，供 REST、兼容的 `news_v2` 投影和 MCP 适配器共同调用。
- Provider 执行级 failover、来源 allowlist、健康/超时分类、每次尝试的可审计 provenance；多源候选可来自 F01 持久化证据、受控实时 Provider、Milvus 候选召回和只读知识图谱关键词扩展。
- 将 F01 的三条已注册 HTTP run/SSE 路由**扩展为** C0 四条（仅增加 run-scoped evidence GET）、五个冻结 MCP 工具、versioned cross-repo fixture manifest 和 HTTP/MCP 等价性测试。
- 新闻再展示/证据访问的许可过滤，以及行情的币种、单位、复权、市场时区、数据可用时间显式化。
- 让 `news_v2` 不再绕过许可/来源策略；它仍是过渡兼容端点，不取代 C0 `/research/*`。

### Out of scope

- F01 的数据库迁移、Evidence/Claim/ResearchRun 状态机、事件表、principal 身份提供者或 SSE 重放实现；F02 只调用其已合并的公开接口。
- F03 的研究 Flow、LLM 路由、数值校验或生成研究结论；F02 只能创建/查询 F01 run，不能自行将结果标为 completed。
- 修改 `AgenticX/` 嵌套 checkout、Near UI、A01/A02 代码，或修改 `AgenticX` Core runtime。
- 图谱构建/更新/删除、向量重嵌入/重建、爬虫重写、购买付费新闻、任意 URL 抓取、真实或模拟交易。
- 将 `StockDataService` 的 `_generate_mock_kline()`、`_get_mock_*()` 或 Alpha Mining mock 数据暴露为 C0 行情/证据。

## 4. 拟修改文件与所有权边界

| 路径 | 动作 | 目的/边界 |
|---|---|---|
| `backend/app/financial/providers/base.py` | 修改 | 扩展 Provider 元数据与 typed 尝试/失败分类所需的最小抽象；现有来源默认 **未获全文再展示许可**，不能以默认值放宽。 |
| `backend/app/financial/registry.py` | 修改 | 在现有 `get_fetcher()` 之外增加按优先级、来源政策和 data type 执行的 failover；保留已有选择 API 的兼容语义。 |
| `backend/app/financial/read_service.py` | 新增 | 唯一的 HTTP/MCP 领域编排、实体扩展、候选过滤、provenance/envelope 构造与 F01 published Port 适配边界。 |
| `backend/app/financial/contracts.py` | 新增 | v1 输入/输出模型、统一 envelope、市场口径和对 F01 `research_ports.py` 的 typed adapter；字段含义严格引用 C0，不另造第二份 Evidence/Run 状态机或 Port 协议。 |
| `backend/app/financial/tools.py` | 修改 | 将 `FinancialNewsTool`/`StockPriceTool` 改为复用 failover/typed provenance，或明确作为内部兼容层；不把它们直接注册为 MCP 工具。 |
| `backend/app/api/v1/research.py` | **修改/扩展（F01 已创建）** | 在 F01 已注册的 C0 `/research` router 上只增加 `GET /evidence/{id}`，并复用其 principal dependency、audit/exception mapping 和 `ResearchRunServicePort` binding；不得重写前三条端点或新增另一 router。 |
| `backend/app/api/v1/__init__.py` | **不修改** | F01 已在 v1 aggregator 注册 `research.router` 到 `/research`；F02 不得重复 include 或变更该注册。 |
| `backend/app/api/v1/news_v2.py` | 修改 | 改走公共读服务的安全投影；让全文字段可按许可省略/替换为允许的 excerpt，并在 OpenAPI 中标记过渡性质。 |
| `backend/app/mcp/__init__.py`、`backend/app/mcp/finnews_server.py` | 新增 | 官方 MCP SDK 服务端与显式启动入口；只绑定五个冻结工具、共享 `FinancialReadService`，支持经认证的 remote streamable HTTP（测试可用 stdio）。 |
| `backend/requirements.txt` | 修改 | 加入与 AgenticX 消费端兼容且有上限的官方 MCP SDK 版本（例如 `mcp>=1.0.0,<2`）；实施时验证与当前 Python/FastAPI 的兼容性。 |
| `backend/tests/financial/test_f02_provider_failover.py`、`test_f02_read_service.py`、`test_f02_mcp.py` | 新增 | Provider、策略/时点、MCP 工具表及等价性单测。 |
| `backend/tests/api/test_f02_headless_api.py`、`backend/tests/financial/test_f02_contract_fixtures.py`、`backend/tests/fixtures/f02/manifest.v1.json`、`backend/tests/fixtures/f02/v1/*.json` | 新增 | ASGI 授权/路由测试和带 producer/consumer/哈希的跨仓稳定 JSON fixture manifest；A02/A03 按 manifest 消费，不能把零散五个成功样例当完整契约。 |

**明确不修改：** `backend/app/api/v1/__init__.py`（F01 已拥有 research router 注册）、`backend/app/storage/vector_storage.py`、`backend/app/knowledge/graph_service.py`、`backend/app/api/v1/knowledge_graph.py`、`backend/app/api/v1/agents.py`、`backend/app/api/v1/alpha_mining.py`、`backend/app/services/stock_data_service.py`、既有 `backend/app/api/v1/news.py` 及 `AgenticX/`。F02 只读取 `get_vector_storage().search_similar()` 和 `get_graph_service().get_search_keywords()` 的结果；若实现发现 F01 无法将 `news_id` 映射到授权的 Evidence，或向量/图谱读取接口本身必须更改，停止实施并另行拆分计划，不能在本 PR 偷改这些基础设施。

## 5. 功能需求与实施意图

### FR-1：公共读服务、来源政策与多源候选收敛

**Before：** `news_v2`、`FinancialNewsTool` 和未来 MCP 将各自直调 Fetcher；向量 `text` 可脱离证据/权限被返回，图谱也可能混入写操作。

**After：** `FinancialReadService` 是唯一编排入口。检索先标准化 entity/query，再以只读图谱关键词扩展，合并 F01 授权的持久 Evidence、向量候选的 Evidence 回查和受策略允许的实时 Provider；每项在返回前经 principal、`available_at <= as_of`、许可和去重过滤。图谱/向量仅改善召回，均不独立构成事实证据。

```text
search_articles(principal, request):
    assert request.as_of is explicitly supplied and timezone-aware
    keywords = readonly_graph_keywords(request.entity_ids)       # 查询失败则只记录 availability，不写图
    candidate_ids = vector.search_similar(...)                   # 只取 opaque news_id，不展示 payload.text
    evidence = F01.EvidenceRepositoryPort.search(principal, query, candidate_ids, request.as_of, run_id=request.run_id?)
    if live refresh is policy-allowed:
        fetched = registry.fetch_with_failover("news", query, source_policy)
        evidence += F01.EvidenceRepositoryPort.register_idempotently(principal, complete_metadata(fetched), RegistrationContext(as_of=request.as_of, run_id=request.run_id?))
    return envelope(filter_authorized_time_license(evidence), provenance)
```

`as_of` 对 `search_articles` 是必填、非 null 的外部参数；省略、naive、未来/不合法值均在调用 Provider/向量前拒绝。可选 `run_id` 只用于研究执行上下文：提供时必须是当前 principal 所有的 run，且 `as_of` 精确等于 `run.as_of`，F01 Port 才可原子绑定合格结果进入该 run snapshot；没有 `run_id` 的预览搜索绝不声称结果属于任何 run，也不能绕过之后 `get_evidence` 的 run-scoped 读取。

F01 已计划提供“principal-scoped 查询、按 `run_id` 获取、携带明确 `RegistrationContext.as_of` 的受控幂等 Evidence 登记”的公开 typed Port。F02 必须对其 `port_version` 做启动/contract-test 校验，且只能传入完整 C0 metadata；不得在 F02 新建平行 evidence 表、平行 principal 或直接将 Provider 正文伪造为 `EvidenceV1`。F01 因未知许可、缺 `available_at`/时区、`available_at > RegistrationContext.as_of` 或 metadata 冲突拒绝登记时，F02 记录安全的 provenance/availability 并排除该候选，不能补默认值。

### FR-2：真实 Provider 的执行级 failover 与 provenance

**Before：** `ProviderRegistry.get_fetcher()` 选择优先级最高的支持者，但 fetch 失败时不尝试备选；`FinancialNewsTool` 只报一个字符串错误。

**After：** 新的 registry 执行 API 按优先级遍历**已启用、许可等级满足当前输出、健康可用且支持 data type**的 Provider。每个尝试记录 provider、开始/结束时间、耗时、结果数、分类失败码和选择/跳过理由。调用者固定某 Provider 时默认不悄悄换源；只有显式允许 fallback 且候选也通过相同政策时才切换。所有失败返回结构化 `source_unavailable`，不吞错后伪造空成功。

```text
for provider in eligible_providers(type, policy, preference):
    try:
        rows = await provider.get_fetcher(type).fetch(params)
        record_attempt(provider, "selected", count=len(rows))
        return rows, attempts
    except (timeout, transport, parse, empty_result) as exc:
        record_attempt(provider, classify(exc))
raise SourceUnavailable(attempts=attempts)
```

来源政策默认拒绝“unknown/未批准”来源的全文再展示；`license_scope=no-redisplay` 仅返回允许的最少来源元数据，不能将正文、向量 payload 或日志作为绕过渠道。真实网络 Provider 只在隔离 staging 配置有已批准来源时验收；本 PR 的 CI 使用确定性 fake Fetcher，不宣称公网来源稳定或已获许可。

### FR-3：行情快照口径、可用性与 mock 隔离

**Before：** `StockPriceTool` 寻找当前没有默认注册的 `stock_price` Fetcher；`StockDataService.get_kline_data()` 失败时可能产生 mock K 线，且其格式没有 C0 要求的行情口径/来源时间。

**After：** `get_market_snapshot` 只从经来源政策批准、能提供数据时间和许可/可用性元数据的 `market_snapshot`/`stock_price` adapter 返回结果；每项显式含 symbol、currency、price/volume/turnover 的 unit、adjustment、market timezone、observed/available/fetched time、provider 和 license status。没有合格 Provider、数据时间未知、`as_of` 早于可用时间、或任一数据源走到 mock 分支时，返回有 provenance 的 `data_unavailable`/`needs_review`，绝不返回模拟数值。

```text
snapshot = approved_market_provider.fetch(...)
if not snapshot or snapshot.is_mock or missing(snapshot.observed_at, currency, unit, timezone):
    return unavailable(reason="market_data_not_verifiable", attempts=attempts)
if snapshot.available_at > request.as_of:
    return unavailable(reason="not_available_as_of", attempts=attempts)
return envelope(snapshot, source=provenance)
```

这不要求在本节点购买/接入新的付费行情；产品/法务未批准来源时，冻结工具仍存在但安全降级为不可用，不能借 AkShare 现有 mock fallback 冒充真实快照。

### FR-4：C0 HTTP 适配与 `news_v2` 安全收口

**Before：** F01 已创建并注册 `/research` 的 run/SSE router，但尚未提供 evidence 读取；`news_v2` 在无 principal/许可检查下直接返回抓取正文；`agents.py` 的内存日志不能作为业务 run。

**After：** F02 仅**扩展 F01 已挂载的** `research.py`，加入第四条 C0 路径 `GET /evidence/{id}`；不触碰 `api_router.include_router`、不重建 `POST /runs`/run GET/SSE handlers。该端点要求 `run_id` query context，并把 principal、run_id、evidence_id 交给 F01 `EvidenceRepositoryPort.get`：Port 必须先授权当前 principal 是 run owner，再验证 Evidence 属于该 run snapshot 且 `available_at <= run.as_of`，最后按许可返回投影。任何缺少/无效 `run_id`、跨 principal、snapshot 缺失、时点倒挂或许可不允许都 fail closed（跨 principal 保持 F01 的 404 anti-enumeration 语义）。`news_v2` 调用公共服务返回安全投影，不能直接调用 `FinancialNewsTool` 后回填原 `content`。

```text
HTTP POST /research/runs:
    # F01-owned existing handler; F02 neither recreates nor registers it
    return F01.ResearchRunServicePort.create_or_reuse(...)

HTTP GET /research/evidence/{id}?run_id=<run_id>:
    principal = F01.require_principal(request)
    require query.run_id
    evidence = F01.EvidenceRepositoryPort.get(principal, run_id=query.run_id, evidence_id=id)
    # F01 has already enforced owner + snapshot membership + available_at <= run.as_of
    return redact_by_license(evidence)
```

不得借用/修改 `agents.execution_logs` 或 `debate_results` 的内存状态，也不得在 F02 提前运行 F03 的研究工作流。

### FR-5：五个冻结 MCP 工具与 HTTP/MCP 等价性

**Before：** 后端不存在 MCP 服务端，当前 AgenticX 中的 `MCPServerConfig` 只是消费者配置，无法保证业务身份、返回 schema 或工具 allowlist。

**After：** `finnews_server.py` 使用官方 MCP SDK 仅注册下表五个处理器。处理器薄适配到同一 `FinancialReadService`/F01 Port；除 transport/context 到 principal 的转换外，不复制搜索、授权或 provenance 逻辑。远程模式只允许 HTTPS streamable HTTP；测试使用 stdio。服务拒绝 `X-AGX-Desktop-Token`，只接受由金融服务验证的 audience-bound、短期凭据（remote 模式为 `Authorization` header；stdio 模式由受控进程注入等价短期凭据）。

| MCP 工具 | 调用的公共能力 | 权限与硬限制 |
|---|---|---|
| `finnews.search_articles` | `FinancialReadService.search_articles` | `research:read`；`as_of` 为必填、带时区输入（可带 run context，带时须等于该 run 的 `as_of`）；没有任意 URL/SQL 参数；按 Evidence 许可、时点和范围过滤。 |
| `finnews.get_evidence` | F01 `EvidenceRepositoryPort.get` + 许可投影 | `research:read`；`run_id` 为必填，必须是当前 principal 所有的 run；Port 验证 snapshot membership 和 `available_at <= run.as_of` 后才可读取。 |
| `finnews.get_market_snapshot` | `FinancialReadService.get_market_snapshot` | `research:read`；无合格来源时明确不可用，不生成 mock。 |
| `finnews.start_research` | F01 `create_or_reuse` | `research:create`、配额与审计；只创建受限研究 run，绝无交易/经纪接口。 |
| `finnews.get_run` | F01 run Port | `research:read`；跨 principal 返回 F01 定义的 403/404，不泄露存在性。 |

所有结果使用同一 v1 JSON envelope，至少含 `schema_version: "v1"`、带时区 `as_of`、`source`（含实际 selected provider/attempts/availability）和 `license_status`。`search_articles` 的 schema 把 `as_of` 标为 required，`get_evidence` 的 schema 把 `run_id` 标为 required；缺参在调用任何 Port/Provider 前拒绝。工具清单、输入 schema、拒绝结果和成功结果固定为 versioned fixture manifest；不得增加“调试”“爬取”“写图谱”旁路工具。

## 6. 验收测试（实施后必须执行）

所有测试禁止真实网络、Neo4j、Milvus、数据库和付费数据依赖；通过 F01 Port fake、假的图谱/向量候选和 fake Provider 断言行为。每个新增测试须先红后绿，测试数据中的 `available_at`、`published_at`、`fetched_at` 都使用明确时区。

| 测试文件 | 最小断言 | 命令 |
|---|---|---|
| `backend/tests/financial/test_f02_provider_failover.py` | 优先 Provider 抛 timeout 后备用 Provider 被调用且成功；attempt 顺序/失败码/selected provider 完整；请求 pin Provider 时不切换；所有 Provider 失败返回 `source_unavailable` 而非假成功；`unknown`/`no-redisplay` 不能产生全文。 | `cd backend && PYTHONPATH=. pytest -q tests/financial/test_f02_provider_failover.py` |
| `backend/tests/financial/test_f02_read_service.py` | 向量 `news_id` 必须经 F01 evidence Port 二次验证；`available_at > as_of` 的候选被剔除；无访问范围的 Evidence 不出现；只读图谱关键词可扩展查询但 mock graph/vector 不能成为证据；缺少验证行情口径返回不可用。 | `cd backend && PYTHONPATH=. pytest -q tests/financial/test_f02_read_service.py` |
| `backend/tests/api/test_f02_headless_api.py` | F01 原有 `POST /runs`/run GET/SSE handler 的 object identity/route count 不变且没有第二次 include；`GET /api/v1/research/evidence/{id}` 缺 `run_id` 为 4xx，principal B、非 snapshot Evidence、`available_at > run.as_of` 均无法读取；F01 约定的跨 principal 404 保持；SSE 仍委托 F01 而不是 `agents.py`。 | `cd backend && PYTHONPATH=. pytest -q tests/api/test_f02_headless_api.py` |
| `backend/tests/financial/test_f02_mcp.py` | MCP `list_tools` 的集合**恰好**等于五个 C0 名称；`search_articles` 缺/naive `as_of` 与 `get_evidence` 缺 `run_id` 都在读服务前拒绝；每一个成功/拒绝调用与同 principal HTTP/公共服务结果有相同 `schema_version`、`as_of`、source、许可投影；缺失/桌面 token、交易关键词或未注册工具 fail closed。 | `cd backend && PYTHONPATH=. pytest -q tests/financial/test_f02_mcp.py` |
| `backend/tests/financial/test_f02_contract_fixtures.py` 与 `backend/tests/fixtures/f02/manifest.v1.json` | 校验 manifest 的 `fixture_set_version`、C0/Port schema version、producer、consumer（A02/A03/F03）、SHA-256、JSON Schema 与弃用规则；逐项校验 success、缺 `as_of`/`run_id`、跨 principal、license/no-redisplay、`available_at` 倒挂、provider/market unavailable、queued/started/step/claim/terminal `RunEventV1`、`Last-Event-ID` replay/no-duplicate、failed/needs_review/cancelled 错误状态。**不得断言五个结果样例已足够。** | `cd backend && PYTHONPATH=. pytest -q tests/financial/test_f02_contract_fixtures.py` |

完整回归命令：

```bash
cd backend && PYTHONPATH=. pytest -q \
  tests/financial/test_smoke_openbb_models.py \
  tests/financial/test_smoke_openbb_provider.py \
  tests/financial/test_smoke_openbb_tools.py \
  tests/financial/test_f02_provider_failover.py \
  tests/financial/test_f02_read_service.py \
  tests/financial/test_f02_mcp.py \
  tests/financial/test_f02_contract_fixtures.py \
  tests/api/test_f02_headless_api.py
```

`manifest.v1.json` 是 A02/A03 的唯一 fixture discovery index，而非五个示例的目录列表。它必须列出每个文件的稳定 ID、HTTP/MCP/SSE transport、请求、预期状态/headers/body 或 SSE transcript、schema/fixture-set/C0 version、SHA-256、敏感字段 redaction、producer 和 consumer；新 fixture-set 只能以新 manifest version 发布，旧版至少保留一个兼容窗口。F01 可提供持久 run/SSE replay 的 canonical producer fixture；F02 负责将其连同本节点 HTTP/MCP/error fixtures 编入 manifest；F03 合并后可按同一 versioning 规则追加 Flow 产生的 `needs_review`/`completed` trace fixture，不能覆盖 F01 事件语义。A02/A03 必须读取 manifest 并验证 digest/版本，不能硬编码文件名或把 live 服务当 fixture。

隔离 staging 冒烟（仅在批准的金融服务凭据、HTTPS 证书、来源许可清单及 F01 迁移均就绪后）还必须验证：首选真实新闻 Provider 超时、备选成功时返回实际 failover；未经许可正文不出现；MCP 远程 `Authorization` 与同一 HTTP principal 的可见范围一致，且 `get_evidence(run_id)` 不越过 snapshot/time boundary。该冒烟不能以公网短暂成功、mock 行情或量化收益替代。

## 7. 失败处理、停止条件与回滚

| 触发 | 运行时行为 | 回滚/处置 |
|---|---|---|
| Provider 超时、解析失败或空结果 | 尝试同策略下的下一个 Provider；响应保留 attempts。全部失败时结构化不可用，不伪造空成功/模拟数据。 | 从来源 allowlist 禁用故障 Provider；保持已持久化、合规 Evidence 的只读可用性。 |
| 许可未知、`no-redisplay`、正文/向量 payload 泄露风险 | metadata-only 或拒绝；日志/fixture/MCP 响应都不写正文。 | 立即禁用该 Provider 的再展示策略；不删改 F01 证据账本，按其审计/保留规则处置。 |
| `available_at > as_of`、时区/行情单位缺失、数字来源不可验证 | 排除候选或返回 `needs_review`/`data_unavailable`；不得形成事实型输出。 | 停用对应适配器，补充来源映射和测试后再启用。 |
| 身份、权限、远程 HTTPS 或 MCP transport 异常 | HTTP/MCP fail closed；不透传 Near 本机 desktop token，不降级为匿名数据。 | 撤销金融服务短期凭据/关闭 MCP 启动入口；Near 保留通用聊天，由 A02/A03 自行处理连接状态。 |
| F01 Port、迁移、principal/snapshot 语义未合并或与 C0 不兼容 | **停止实施**，不得为赶进度新建平行表、内存 run、router 重注册或授权绕过。 | 先修订/合并 F01 或 C0，再重新验证 manifest fixtures。 |

本节点原则上没有 schema migration；回滚应优先移除 F02 增加的 evidence handler、MCP 服务进程/配置和新增来源策略，**不得移除 F01 拥有的 `/research` router 注册或三条 run/SSE handler**，更不得删除 F01 的审计证据或 run。若实现需要迁移，必须停止并拆分为经 F01 审核的迁移计划。

## 8. 依赖、交付物与后续协作

1. **硬前置 F01：** 已合并并文档化的 principal dependency、`research:read`/`research:create` 权限、versioned `EvidenceRepositoryPort`/`ResearchRunServicePort`、complete-metadata idempotent registration、owner/snapshot/`available_at <= run.as_of` 的 get/search、`request_id` 幂等、事件 SSE、至少一个不泄露全文的证据投影。F02 开始时记录实际 module path、port version、composition-root binding、F01 PR/commit 和 F01 producer fixture digest。
2. **来源治理前置：** 产品/法务提供每个启用 Provider 的许可范围、允许的再展示等级、期限和停用开关；没有书面/配置化结论即为 `unknown`，不是默认许可。
3. **MCP 前置：** 锁定官方 SDK 版本并在干净后端环境验证；部署提供 HTTPS 证书、短期金融服务 token 签发/轮换和审计。AgenticX A01/A02 不是 F02 的代码前置，但 A02/A03 只能消费本计划交付的 `manifest.v1.json` 所列 fixture，不能要求 F02 修改 `AgenticX/`。
4. **对 F03/A02/A03 的交付：** versioned manifest、JSON/SSE transcript fixtures、OpenAPI、五个 MCP 工具 schema、required `as_of`/`run_id` 参数、失败码和 provenance/availability/许可字段说明。manifest 覆盖 run 生命周期、replay 与 error states；F03 在此基础上做研究 Flow 并可按 manifest 规则追加其 terminal trace，A02/A03 再做连接/UI 展示。

## 9. 独立实施分支与 PR

F01 合并且从 FinnewsHunter 最新 `main` 开始后，建立独立分支：

```text
feat/finance-f02-headless-mcp
```

PR 建议标题：`feat(finance): add F02 headless research API and read-only MCP boundary`。

该 PR 仅包含本计划列出的 FinnewsHunter 文件、测试与 fixtures；正文必须写明 C0 version、F01 PR/commit 依赖、来源许可清单状态、完整测试命令/结果、未启用的行情来源以及给 A02/A03 的 fixture 路径。不得提交嵌套 `AgenticX/` checkout，不得把 F02 与 F03、Near UI、交易或图谱写入混在同一 PR。合并门槛遵从 Master Plan：F01 后向兼容/迁移测试已绿，且本计划 HTTP/MCP/fixture/安全失败路径全部通过。
