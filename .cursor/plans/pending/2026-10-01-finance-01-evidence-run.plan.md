# F01：证据时点、研究运行状态与权限实施子计划

Planned-with: Manus
Suggested-Impl-Model: **代码专精中档 + 强推理审查**；本节点同时涉及 PostgreSQL 迁移、幂等并发、鉴权、审计和 SSE 回放，实施模型应擅长 FastAPI/SQLAlchemy，审查者须专门复核时点、越权和事务边界。
Parent-Plan: [2026-10-01-finance-agent-master.plan.md](2026-10-01-finance-agent-master.plan.md)
Plan-Id: 2026-10-01-finance-01-evidence-run
Plan-Type: 实施子计划 F01（**待评审、待实施**）

> 本文只定义 F01 的实施步骤和验收口径，不代表任何功能、迁移、分支、提交、推送或 PR 已经完成。执行前先按父计划将本文件从 `.cursor/plans/pending/` 移至 `.cursor/plans/`；不得在父仓库提交嵌套的 `AgenticX/` checkout。

## 1. 目标、冻结契约与 DAG 位置

在 **1–2 周**内，为 FinnewsHunter 建立受保护、可审计、可重放的研究运行基础：持久化 `EvidenceV1`、`ClaimV1`、`ResearchRunV1` 和 `RunEventV1` 的领域记录；以同一个远程 principal 和 scope 保护研究运行；让相同 `principal_id + request_id` 的重试稳定返回同一运行；让断线客户端以 `Last-Event-ID` 从数据库事件账本无重复续读。

本节点严格服从父计划的冻结 C0：

- `available_at` 是系统实际获得证据的时间，**不得**用 `published_at` 静默替代；对外时间均为带时区的 ISO-8601。
- `fact` Claim 必须关联证据；该证据须属于同一研究快照且 `available_at <= run.as_of`。`inference` 与 `hypothesis` 必须保留显著类型标记。
- Run 状态只使用 `queued`、`running`、`needs_review`、`completed`、`failed`、`cancelled`；每个 RunEvent 的 `seq` 在同一 `run_id` 中严格递增。
- 认证、授权、审计失败均 fail closed；不得把 Near 本机 token 或现有 `SECRET_KEY` 当作金融 API 的远程认证凭据。

DAG 上，F01 的唯一前置是 **C0 已在双方规划 PR 中审阅通过**；它可以与 AgenticX 的 A01 并行。F02 只有在 F01 的迁移、鉴权、幂等、后向兼容、已文档化 typed Port 与 dispatch-hook 测试通过后才能依赖本节点；F03 的 Flow/I01 不是本节点的实现范围，但 F01 必须交付使 F03 无需改动 F01/F02 模块即可挂接的 durable worker-dispatch hook。

## 2. 当前基线、根因与证据

| 观察 | 当前代码锚点 | 对 F01 的含义 |
|---|---|---|
| 新闻只有 `publish_time`、`created_at`、`updated_at`，均为未指定 `timezone=True` 的 `DateTime`，且没有许可、内容哈希、系统可得时点或证据实体。 | `backend/app/models/news.py:24-30` | 不能把历史 `News` 直接当作符合 C0 的 Evidence，更不能把抓取时间或发布时间猜成 `available_at`。 |
| `Analysis` 仅以 `news_id` 关联新闻，保存的是分析文本/情感/模型名，不含可验证 Claim、Evidence 链接或研究运行。 | `backend/app/models/analysis.py:17-47` | 不能将旧分析文本重命名为 Claim，也不能把它当作事实证据。 |
| `agents.py` 使用进程内 `execution_logs` 与 `debate_results`；普通辩论与 SSE 辩论各自生成数据，进程重启和多实例都会丢失状态。 | `backend/app/api/v1/agents.py:198-204`、`285-472`、`477-845`、`1146-1308` | F01 必须新增持久化研究账本，不能将内存 dict 误称为 ResearchRun 的权威来源。 |
| API 根路由已由 `api_router` 统一挂载，`agents` 已在 v1 聚合器下以 `/agents` 注册。 | `backend/app/main.py:251-252`；`backend/app/api/v1/__init__.py:10-23` | 研究路由应作为新的 `/research` 子路由注册，而不是改写或挤占旧 `/agents/*` 路径。 |
| 运行时会话在 `get_db()` 的 yield 后统一提交/回滚；模型初始化仍使用 `Base.metadata.create_all`。 | `backend/app/core/database.py:14-34`；`backend/app/models/database.py:83-94`；`backend/init_db.py:23-40` | 关键的 run 创建、事件追加、审计必须在明确事务内完成；研究表不能依赖无版本的 `create_all` 完成生产迁移。 |
| 已声明 `alembic>=1.12.0`，但仓内尚无 `alembic.ini` 或版本目录；`start.sh` 只调用 `python init_db.py`。 | `backend/requirements.txt:8-12`；`backend/start.sh:25-29` | F01 需建立最小 Alembic 运行环境，并保留旧表启动路径的兼容性。 |
| 现有配置只有泛用 `SECRET_KEY` 与过期时间；仓内未发现 JWT/OAuth2/HTTP Bearer 验证实现。 | `backend/app/core/config.py:165-167`；`backend/env.example:137-139` | 研究 API 不能假定现有用户认证已存在，须显式引入可配置、可验证的远程 bearer principal 机制。 |

## 3. 范围

### 纳入范围

1. 新增、版本化的研究领域表及其 Alembic 迁移：Evidence、Claim、Claim–Evidence 链接、ResearchRun、RunEvent 和最小化访问审计记录。
2. 研究专用 bearer-token 验证、principal/scope/实体范围授权以及不记录 token、原文或受限全文的审计。
3. `POST /api/v1/research/runs`、`GET /api/v1/research/runs/{id}` 与 `GET /api/v1/research/runs/{id}/events` 的**受保护运行账本接口**，包括 `request_id` 幂等、状态转换守卫和 `Last-Event-ID` 重放。
4. 对证据时点、Claim 证据链接、许可安全载荷和事件序列的内部服务层校验，以及 PostgreSQL 集成测试。
5. 面向 F02 的公开、typed `EvidenceRepositoryPort` / `ResearchRunServicePort`，以及面向 F03 的 durable task-dispatch/worker hook；二者均复用同一 principal、snapshot、审计和状态机。
6. 将研究表迁移接入现有启动路径，但不破坏旧新闻、分析和智能体 API。

### 不纳入范围

- `GET /api/v1/research/evidence/{id}`、新闻检索、行情口径、OpenAPI/MCP 工具、契约 fixture 和 provider 降级：由 **F02** 交付。
- 实际 Research Flow、模型路由、数值核验、Claim/Brief 生成或将 `queued` Run 执行为 `running/completed`：由 **F03** 交付。
- Near UI、桌面凭据存储、AgenticX MCP 远程适配：分别属于 A02/A03/A01。
- 将历史 `news` 行批量回填为 Evidence、猜测其时区/许可/`available_at`，或把现有 `Analysis.analysis_result` 转换为事实 Claim。
- 交易、券商、账户、付费新闻购买、删除研究证据、跨 principal 共享或企业多租户/HA。

## 4. 文件边界与当前锚点

### 计划新增或修改的文件

| 文件 | 动作 | 当前锚点 / 实施意图 |
|---|---|---|
| `backend/requirements.txt` | 修改 | 在现有 `alembic>=1.12.0`（第 8-12 行）附近加入经过安全审查的 JWT/JWK 验签依赖；不自行使用 `SECRET_KEY` 签发金融 token。 |
| `backend/requirements-dev.txt` | 新增 | 声明 `pytest`、`pytest-asyncio` 等 F01 测试所需开发依赖，避免把测试依赖误当作现有运行时承诺。 |
| `backend/app/core/config.py` | 修改 | 在 `Settings` 的安全配置区（第 165-167 行）新增研究认证 issuer、audience、JWKS URL、允许算法、必需 scope、SSE 轮询/上限及版本标识配置；生产无完整验证配置时研究路由 fail closed。 |
| `backend/app/core/research_auth.py` | 新增 | 提供可替换的 bearer principal 验签、scope 解析、实体范围判断及脱敏审计上下文；只输出 `principal_id` 与批准的 scope，不输出 token。 |
| `backend/app/models/research.py` | 新增 | 定义 `Evidence`、`ResearchRunEvidence`（不可变 run snapshot 成员关系）、`Claim`、`ClaimEvidence`、`ResearchRun`、`RunEvent`、`ResearchAuditEvent` 与 `ResearchDispatchOutbox` ORM 模型及关系；外部 C0 字段由该模型/序列化层权威映射。 |
| `backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/versions/<revision>_f01_research_ledger.py` | 新增 | 建立仓内目前缺失的 Alembic 配置，并以显式版本化 DDL 新增研究表、snapshot/outbox 约束和索引；不得对 `news`、`analyses` 或历史数据做破坏性变更。 |
| `backend/app/services/research_ports.py` | 新增 | F01 **公开且稳定**的 Pydantic/`Protocol` 边界：`EvidenceRepositoryPort`、`ResearchRunServicePort`、其 typed command/query/result 和版本号；F02/F03 只能经此边界，不得直接查询研究 ORM。 |
| `backend/app/services/research_runs.py` | 新增 | `ResearchRunServicePort` 的事务实现：规范化请求哈希、状态转换、证据/Claim 校验、串行事件追加、审计写入、snapshot 查询与回放；供路由和未来 F03 worker 共用。 |
| `backend/app/services/research_evidence.py` | 新增 | `EvidenceRepositoryPort` 的事务实现：complete-metadata 幂等登记、principal-scoped get/search、run snapshot 绑定及许可/`as_of` fail-closed 投影。 |
| `backend/app/services/research_dispatch.py` | 新增 | F01 拥有的 `ResearchRunDispatcherPort`、persistent outbox drainer 和固定 task-name 契约；新建 queued run 提交后可靠分派，F03 只在自己的 worker 文件注册该 task。 |
| `backend/app/api/v1/research.py` | 新增 | 定义运行创建、读取与 SSE 回放的 Pydantic v1 形状和受保护端点；本阶段不实现 evidence 查询或 MCP。 |
| `backend/app/api/v1/__init__.py` | 修改 | 以当前 `include_router(agents.router, prefix="/agents")`（第 20 行）同级方式注册 `research.router` 至 `/research`；不改变既有前缀。 |
| `backend/init_db.py`、`backend/start.sh` | 修改 | 保持第 23-40 行所导入的旧模型和旧表 bootstrap；在其后显式运行 `alembic -c alembic.ini upgrade head`，且研究迁移失败时不得启动应用。 |
| `backend/env.example` | 修改 | 在现有安全配置段（第 137-139 行）增加仅为变量名称/说明的研究认证样例，不提交 issuer 私钥、token 或真实 JWKS 凭据。 |
| `backend/tests/research/conftest.py`、`test_f01_migration_schema.py`、`test_f01_evidence_claims.py`、`test_f01_ports_dispatch.py`、`test_f01_auth_idempotency.py`、`test_f01_event_replay.py`、`test_f01_legacy_routes.py` | 新增 | 使用隔离 PostgreSQL 数据库、测试 JWK、fake task transport 与固定时钟验证迁移、Port 时点/许可/范围、outbox 分派、并发幂等、SSE 重放和旧路由存在性。 |

### 明确不修改的文件（及原因）

| 文件 | 当前锚点 | F01 的约束 |
|---|---|---|
| `backend/app/models/news.py` | `News.publish_time/created_at` 位于第 28-30 行，`to_dict()` 位于第 59-77 行 | 不将旧 naive 时间列改成新时点语义，也不追加伪造 `available_at`；Evidence 以独立、可审计快照表存放。 |
| `backend/app/models/analysis.py` | `Analysis.news_id` 位于第 20 行，`analysis_result` 位于第 27 行 | 不重解释历史分析为 Claim，不更改 `analyses` 表或其 API 返回。 |
| `backend/app/api/v1/agents.py` | 内存存储在第 198-204 行；旧日志/指标/清理端点在第 1146-1308 行 | 保持 `/api/v1/agents/*` 的响应、内存语义和路径不变；新账本仅服务 `/research/*`，不进行“悄悄替换”。 |
| `backend/app/main.py` | `FastAPI(...)` 位于第 109-119 行，v1 路由挂载位于第 251-252 行 | 不改动全局 CORS、Docs CSP、异常处理或主前缀；F01 仅通过 v1 聚合器接入，避免影响所有旧端点。 |
| `backend/app/core/database.py` | `get_db()` 位于第 14-34 行 | 保留现有依赖给普通短请求使用；SSE 回放轮询由研究服务按批次新建/关闭会话，不让流跨越已结束的请求事务。 |
| `backend/app/models/database.py`、`backend/app/models/__init__.py` | `init_db()` 的 `Base.metadata.create_all` 位于第 83-94 行 | 不把研究模型加入旧 `create_all` 导入路径或以它创建研究表；研究 schema 的唯一部署权威是 Alembic revision。 |
| `backend/app/api/v1/news.py`、`backend/app/api/v1/analysis.py` | 新闻写入第 65-149 行；分析端点第 92-294 行 | 不改动既有爬取、新闻查询或分析工作流；后续 F02 才以符合许可/时点的数据接入 Evidence。 |

## 5. 功能需求与实施步骤

### FR-1：用可迁移的独立快照保存证据、主张与运行账本

**改动前**：`News` 和 `Analysis` 是各自的业务表；它们无法表达 C0 的 `content_hash`、许可范围、实体范围、含时区时点、Claim–Evidence 多对多关系或可恢复的研究状态。仓内虽然声明 Alembic 依赖，但没有迁移环境。

**改动后**：建立只增不改的研究领域 schema，所有时间以 PostgreSQL `timestamptz` 和应用层 timezone-aware `datetime` 存储/校验；历史新闻仍是历史新闻，只有完整元数据的新 Evidence 才可进入研究快照。

- `research_evidence` 保存 C0 的 `evidence_id`、`source_id`、`source_url`、`content_hash`、`published_at`、`fetched_at`、`available_at`、`timezone`、`license_scope`、`entity_ids`、`excerpt`、`quality_status`。哈希由受信任写入方基于规范化可许可内容计算；无需也不得在事件/审计中复制全文。`license_scope` 必须是配置化 allowlist 中的明确值；缺失、`unknown`、缺 `available_at`、无 offset 或内容/来源元数据不完整的登记均拒绝，而不是以发布时间、抓取时间或默认许可补齐。
- `research_run_evidence` 以 `(run_id, evidence_id)` 建立 snapshot 成员关系，记录成员加入时的 metadata/version；对 run-scoped 读取只承认该表中的 Evidence。F03 worker 可在已 claim 的 `running` run **证据收集阶段**逐条受控加入 Evidence，每次在同一事务验证 run owner/实体范围、`available_at <= run.as_of` 与许可投影，并追加 `evidence_added` 事件；进入 Claim 生成前由 Port 原子设置 `snapshot_frozen_at`。冻结后成员关系不可变，任何新搜索结果只能开新 run，不能静默改写旧快照。
- `research_claims` 保存 C0 的 `claim_id`、`kind`、`text`、`as_of`、`valid_until`、`confidence` 和所属 `run_id`；`research_claim_evidence` 用外键关联，响应层由它导出 `evidence_ids[]`，以取得真实引用完整性。
- `research_runs` 保存 C0 的全部运行字段，包括 `request_id`、`principal_id`、实体列表、`as_of`、状态、模型/提示词/策略版本、结果引用和错误码；`result_ref`、`error_code` 可在尚未执行的 `queued` 状态显式为 `null`，但响应键不得省略。
- `research_run_events` 保存 C0 Event 字段和最小化 JSON `payload`；建立 `(run_id, seq)` 唯一约束和按 `(run_id, seq)` 回放索引。`research_audit_events` 只记访问决策/资源标识/追踪 ID/时间/结果，不记 token、原文、完整 excerpt 或模型提示词。
- `research_dispatch_outbox` 是新建 run 同一事务写入的 durable dispatch request，唯一键保证每个首次创建的 run 只有一个逻辑执行请求；它不是第二份运行状态，也不暴露为 API。
- 迁移使用新建表、外键、检查约束和索引；状态、Claim kind 与 RunEvent type 的允许值同 C0。此 revision 不 `ALTER` 既有 `news`/`analyses`，不做不可核验的历史回填。

**伪代码意图：**

```text
写入 Evidence：
  typed EvidenceRegistrationCommand 要求所有 C0 EvidenceV1 metadata、来源策略版本及明确 license_scope；typed RegistrationContext 始终要求显式、带时区 as_of（可选 run_id）
  要求 published_at、fetched_at、available_at 均为带 offset 的时间，timezone 非空
  若 available_at 缺失、无时区、许可未知/不允许、内容哈希/来源 URL/实体范围缺失、available_at > context.as_of，或由调用者要求“等同 published_at”补齐，则拒绝写入
  用稳定 source_id + source_url + content_hash + 可得/许可 metadata 指纹幂等登记；冲突元数据返回冲突，不覆盖原证据
  保存内容哈希、许可范围和最小允许的 excerpt；不保存/回传无许可全文

建立 Claim 链接：
  读取 run.as_of 与所有候选 Evidence
  若 kind == fact 且证据列表为空：拒绝
  若任何 Evidence.available_at > run.as_of：拒绝链接并使后续执行可转 needs_review
  否则在同一事务写 Claim 与 ClaimEvidence；响应映射 evidence_ids
```

### FR-2：引入研究专用 principal、范围授权与最小审计

**改动前**：现有配置中的 `SECRET_KEY` 未被研究 API 用于可验证的 bearer principal，仓内没有 JWT/OAuth2 验证器；`/agents/*` 未执行 principal 资源隔离。

**改动后**：仅研究路由使用一个可替换的、验证 issuer/audience/JWKS/允许非对称算法的 bearer 依赖。它从已验证 token 中形成 `principal_id`、scope 集合和实体资源范围；它不信任客户端自报 principal，也不接受 Near 本机 token 作为替代。

- `POST /research/runs` 必须有 `research:create`；读取 run/SSE 必须有 `research:read`，并且默认仅可访问同一 `principal_id` 所有的 run。请求中的每个 `entity_id` 必须落在该 principal 的批准范围内；无跨 principal 复用或枚举。
- 缺少、过期、篡改或 issuer/audience 不匹配的 bearer 返回 401；已认证但 scope/实体范围不足返回 403；访问其他 principal 的资源返回 404，避免存在性泄露。JWK 获取或必要安全配置不可用时返回非成功服务错误并不访问数据。
- 每个创建、读取、事件订阅/回放和拒绝决策写入 append-only `ResearchAuditEvent`；审计写入失败时，受保护操作不得返回数据或成功创建 Run。审计只保存脱敏 principal/资源/结果/请求追踪标识，不保存 Authorization 头。
- 配置的生产验证材料不得给出不安全默认值。测试可以注入临时测试 JWK/验证器；部署时由机密存储提供 JWKS 地址、issuer、audience 和允许算法。

**伪代码意图：**

```text
principal = verify_bearer(Authorization, issuer, audience, jwks, allowed_algorithms)
if principal 不存在：审计拒绝（不含 token）后返回 401
if required_scope 不在 principal.scopes：审计拒绝后返回 403
if requested_entity_ids 不全在 principal.entity_grants：审计拒绝后返回 403
对 run_id 的读取：若 owner != principal.id，审计拒绝后返回 404
审计成功决策后才执行/返回受保护资源
```

### FR-3：发布 F02 可消费的 typed Evidence/Run Port，并为 F03 提供实际 dispatch hook

**改动前**：后端没有研究领域对象；未来 F02 若直接导入 ORM 或自建 evidence 表，会绕开 principal、许可、snapshot 和审计。queued run 也没有一个可由下游 worker 可靠消费的分派点。

**改动后**：F01 在 `app.services.research_ports` 发布带 `port_version="v1"` 的公开类型边界，具体实现隐藏在 F01 服务中。F02 通过依赖注入取得该 Port，**不**重建/重注册 research router，也不直接使用 `research_*` ORM；F03 通过同一 Port 的 worker capability 和固定 task-name 执行 run，不修改 F01/F02 共享路由或服务文件。

- `EvidenceRepositoryPort.register_idempotently(principal, EvidenceRegistrationCommand, RegistrationContext)` 的 command 必填全部 `EvidenceV1` metadata：`source_id`、`source_url`、`content_hash`、`published_at`、`fetched_at`、`available_at`、`timezone`、`license_scope`、`entity_ids`、许可允许的 `excerpt`、`quality_status`，以及 provider/source-policy version；context 的 `as_of` 始终必填且带时区，`run_id` 可选。它用稳定 metadata 指纹返回既有或新 Evidence；同一自然键而任一安全元数据冲突为显式冲突，绝不覆盖。任何 `available_at > context.as_of`、未知/不允许许可或不完整 metadata 均拒绝。带 `run_id` 时还原子绑定 snapshot，并 fail closed 验证 owner、entity grants、`context.as_of == run.as_of`；无 run ID 的登记不自动进入任何 run snapshot。
- `EvidenceRepositoryPort.search(principal, EvidenceSearchQuery)` 与 `get(principal, run_id, evidence_id)` 都是 principal-scoped。`search` 强制显式、带时区 `as_of`，并在提供 `run_id` 时验证 run owner 且 `as_of == run.as_of`；只有该 principal、实体范围、许可投影和 `available_at <= as_of` 全部通过的结果才返回。`get` 强制 `run_id`，验证 owner、`ResearchRunEvidence` membership 与 `available_at <= run.as_of` 后才给出与 license 相符的投影；跨 principal 统一 404，缺 snapshot/时点/许可一律非成功，不能退回全局按 ID 查询。
- `ResearchRunServicePort` 定义 `create_or_reuse`、owner-scoped `get`/event replay、`append_event`、`claim_queued_run_for_execution`、`attach_evidence_before_freeze`、`freeze_snapshot` 与受控 claim 写入等 typed command/result。只有携带内部 `ResearchWorkerCapability` 的 worker 可 claim `queued -> running` 并在该 run 的 `running` 证据收集阶段附加证据；该 capability 从 dispatcher 注入，绝不从客户端 bearer 或 MCP 参数取得。冻结与第一条 Claim 同一事务边界内完成；重复 delivery 对已 claim/终态 run 为幂等 no-op，不能再执行或重置 seq。
- F01 的 `ResearchRunDispatcherPort` 固定传送契约为任务名 `finnews.research.execute_run.v1`，payload 仅含 `run_id`、outbox/request correlation ID 和 contract version，**不**携带用户 bearer、全文或模型输入。首次创建 queued run、审计和 `ResearchDispatchOutbox` 行同事务提交；提交后 drainer 发送任务，只有 transport 确认后标记 dispatched，并以退避重试。幂等 `POST` 重读既有 run 不新增 outbox 行。F03 在其新建 `app/workers/research_flow_worker.py` 注册此准确 task name、以 capability claim run 并运行 Flow；F01 不 import F03，F02 不负责分派。未安装/不可达 worker 时 run 保持 queued 且 outbox 可重试，不能假称 running/completed。

**Port/dispatch 伪代码意图：**

```text
create_or_reuse(principal, request):
  transaction: insert queued run + allowed audit + one dispatch-outbox row
  after_commit: dispatcher.drain("finnews.research.execute_run.v1")
  # idempotent reuse returns the old run and does not enqueue again

F03 task finnews.research.execute_run.v1(run_id, dispatch_id, v1):
  worker_capability = dispatcher.verify_delivery(dispatch_id)
  run = ResearchRunServicePort.claim_queued_run_for_execution(worker_capability, run_id)
  if run is already claimed/terminal: return no_op
  EventStockResearchFlow(...ports...).kickoff_async(run)
```

### FR-4：以唯一键、请求指纹和状态机实现幂等且可审计的运行创建

**改动前**：`agents.py` 根据当前时间和股票代码生成 `debate_id`（约第 301-303 行），结果写进内存 dict，重试会产生不同 ID，且状态不受事务保护。

**改动后**：研究运行创建是数据库事务：同一 principal 的相同 `request_id` 只拥有一个 Run；跨 principal 的同名 request ID 绝不共享。F01 只接受并持久化 `queued` 运行，不调用 LLM、Provider 或交易工具。

- 在 `research_runs` 上建立 `(principal_id, request_id)` 唯一约束；同时保存由 canonical `entity_ids`、`as_of` 和请求版本组成的 request fingerprint，防止同一键承载不同请求。
- 新请求在同一事务中写入 `queued` Run、创建审计记录并提交，创建成功返回 C0 `ResearchRunV1` 形状。相同 principal/键且指纹相同返回原 Run；指纹不同返回 409，不覆盖原请求。并发唯一键冲突须重新读取并比较指纹，而不是返回随机 500。
- 实现只允许 F03 经 `ResearchWorkerCapability` 调用的受控状态转换和事件追加服务：`queued -> running/failed/cancelled`，`running -> needs_review/completed/failed/cancelled`，以及受审查后明确允许的后续转换；终态不得再追加业务事件。写状态、分配事件序号和写事件必须是同一事务。
- 对应 `started`、`needs_review`、`completed`、`failed`、`cancelled` 的事件类型必须与目标状态一致；`step_started`、`evidence_added`、`claim_checked` 不擅自宣布完成。F01 创建的 `queued` Run 不伪造 `started` 或 `completed` 事件。

**伪代码意图：**

```text
fingerprint = hash(canonicalize(request_id, sorted(entity_ids), as_of, schema_version))
begin transaction
  try insert (principal_id, request_id, fingerprint, status=queued, ...)
  except unique_violation:
      existing = select by (principal_id, request_id)
      if existing.fingerprint == fingerprint: return existing
      else: raise IdempotencyConflict(409)
  write audit(action=create_run, outcome=allowed)
commit

append_event(run, event):
  lock run row FOR UPDATE
  validate allowed transition and non-terminal state
  next_seq = persisted last sequence + 1
  write updated run + (run_id, next_seq, event) + audit atomically
```

### FR-5：提供最小运行读取与数据库驱动的 SSE 断线回放

**改动前**：`generate_debate_stream()` 只为当前请求生成 SSE（`agents.py:477-845`），没有 event ID、持久 cursor、重连读取或 principal 所有权检查。

**改动后**：新增的研究路由只输出 C0 研究运行账本，使用持久 `event_id` 作为 SSE `id`。它可在没有 Redis/第二编排引擎的 F01 范围内，以短间隔数据库轮询读取已提交事件；F03 将来只需调用同一 `append_event` 服务。

- `POST /api/v1/research/runs` 创建或幂等读取 queued Run；`GET /api/v1/research/runs/{id}` 返回同一 C0 外形；二者均受 FR-2 权限约束。
- `GET /api/v1/research/runs/{id}/events` 读取 `Last-Event-ID`：缺失时从 seq 1；提供时先验证该 event 属于已授权 run，再仅按 `seq` 升序发送后续事件。无效 UUID、未知 cursor 或属于其他 run 的 cursor 以明确 4xx 拒绝，不猜测位置。
- 每条 SSE 严格输出 `id: <event_id>`、`event: <C0 type>`、`data: <JSON payload>`；payload 只含安全的 ID、状态和原因码，不含受限全文、Authorization 或原始 prompt。已终态且无新事件时正常结束；非终态在配置的最大持续时间内轮询，再由客户端按最后 ID 重连。
- 为避免重复/乱序，服务端只推进到已经成功写入数据库的最大 seq；事务回滚或审计写入失败时不发出 `completed`（也不发出声称成功的 SSE）。

**伪代码意图：**

```text
cursor_seq = 0 if Last-Event-ID 缺失 else lookup_authorized_event_seq(run_id, header)
while 未到流时限：
  events = select events where run_id == run_id and seq > cursor_seq order by seq
  for event in events:
      yield SSE(id=event.event_id, event=event.type, data=redacted(event.payload))
      cursor_seq = event.seq
  if run.status 是终态且没有新事件：结束
  sleep(configured_poll_interval)
```

### FR-6：以安全迁移接入既有启动路径，并锁住旧 API 兼容边界

**改动前**：`backend/start.sh` 只运行无版本的 `init_db.py`；`init_db.py` 已显式导入旧模型后调用 `Base.metadata.create_all`。现有 v1 路由没有 `/research`。

**改动后**：旧表 bootstrap 仍可工作，研究 ledger 由明确 revision 接管；启动脚本在启动 Uvicorn 前执行研究 revision。`api/v1/__init__.py` 新增 `/research` 路由，不修改 `main.py` 的全局装配，也不改变旧路由响应。

- Alembic `env.py` 显式加载迁移所需 metadata，并将研究 revision 作为新 schema 的唯一 DDL 来源；不要把研究模型加进旧 `init_db.py` 或 `models.database.init_db()` 的 `create_all` 导入集合。
- `start.sh` 保留旧 `python init_db.py` 的顺序以兼容现有 `news`/`analyses` 等表，再执行 `alembic -c alembic.ini upgrade head`。第二步失败时依赖现有 `set -e` 停止启动，禁止带缺失事件账本对外服务。
- 新路由在聚合器注册为 `/api/v1/research/*`。F01 不新增 MCP 工具，也不提前开放 evidence 读取端点；F02 扩展时必须沿用同一 principal 依赖和 C0 形状。
- `News.to_dict()`、`Analysis.to_dict()`、`/news/*`、`/analysis/*`、`/agents/*` 的路径和响应保持不变。旧 `execution_logs` 的内存清理不删除任何 `research_run_events`。

## 6. 验收测试与可执行命令

### 测试文件、断言和通过条件

| 测试文件 | 必须验证的断言 |
|---|---|
| `backend/tests/research/test_f01_migration_schema.py` | 在干净 PostgreSQL 上执行 `upgrade head` 后，存在全部研究表；`research_runs(principal_id, request_id)` 与 `research_run_events(run_id, seq)` 为唯一约束；研究时间列为带时区类型；升级不修改 `news` 与 `analyses` 的既有列。 |
| `backend/tests/research/test_f01_evidence_claims.py` | 拒绝没有 offset 的时间、缺失 `available_at` 和以 `published_at` 作隐式补值；`fact` 无证据失败；`available_at > run.as_of` 的 Evidence 不可链接；允许合格的 `inference`/`hypothesis` 并在序列化结果中保留 kind 与 evidence IDs。 |
| `backend/tests/research/test_f01_ports_dispatch.py` | 以公开 `EvidenceRepositoryPort` 验证完整 metadata/明确 license/**必填带时区 `RegistrationContext.as_of`** 的登记要求、`available_at > as_of` 拒绝、相同 metadata 幂等和冲突拒绝；principal B 不能 search/get A 的 Evidence；`get(run_id, evidence_id)` 拒绝非 snapshot 成员、`available_at > run.as_of` 和不允许的许可投影。验证首次创建 run 原子写一条 outbox、幂等重试不再写；fake transport 仅收到固定 v1 task payload，未确认会重试；`claim_queued_run_for_execution` 只接受 worker capability 且重复 delivery 不重复启动/写 seq。 |
| `backend/tests/research/test_f01_auth_idempotency.py` | 无/坏/过期 bearer 为 401；仅 `research:read` 创建为 403；授权 principal 创建 queued Run 成功；同 principal + 相同 request_id + 相同指纹返回同一 `run_id` 且只存在一行；同 principal 键冲突且请求不同为 409；principal B 可用同 request_id 创建自己的 Run，但读取 A 的 Run 为 404；允许与拒绝访问都有脱敏审计行。 |
| `backend/tests/research/test_f01_event_replay.py` | 并发追加不会产生重复或跳号 `seq`；事件与状态转换在同一提交后可见；SSE 第一连接有 `id/event/data`，以第一条 `event_id` 作为 `Last-Event-ID` 重连后只收到后续 seq；其他 Run 的 cursor 和未授权订阅都被拒绝；失败事务不产生 `completed` 事件。 |
| `backend/tests/research/test_f01_legacy_routes.py` | FastAPI 路由表仍包含 `POST /api/v1/agents/debate`、`POST /api/v1/agents/debate/stream`、`GET /api/v1/agents/logs`、既有 `/api/v1/news/` 与 `/api/v1/analysis/news/{news_id}`；新增且仅新增预期的 `/api/v1/research/runs`、`/api/v1/research/runs/{id}`、`/api/v1/research/runs/{id}/events`。 |

### 建议在隔离数据库执行的命令

> F01 使用 PostgreSQL 专有约束、数组和行锁；不得用 SQLite 代替该验收环境。命令中的数据库仅为本地测试库，执行前不得指向真实环境。

```bash
cd /home/ubuntu/FinnewsHunter
docker compose -f deploy/docker-compose.dev.yml up -d postgres
docker compose -f deploy/docker-compose.dev.yml exec -T postgres sh -ec \
  'dropdb -U finnews --if-exists finnews_f01_test; createdb -U finnews finnews_f01_test'

cd /home/ubuntu/FinnewsHunter/backend
python -m pip install -r requirements.txt -r requirements-dev.txt
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=finnews_f01_test \
  alembic -c alembic.ini upgrade head
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=finnews_f01_test \
  alembic -c alembic.ini current
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=finnews_f01_test \
	pytest -q tests/research/test_f01_migration_schema.py \
	          tests/research/test_f01_evidence_claims.py \
	          tests/research/test_f01_ports_dispatch.py \
	          tests/research/test_f01_auth_idempotency.py \
	          tests/research/test_f01_event_replay.py \
            tests/research/test_f01_legacy_routes.py
```

PR 描述必须记录上述命令的实际结果、Alembic revision、测试 JWK 仅在测试中生成的事实，以及没有测试生产 issuer/JWKS 的限制；不可用“模拟收益”或内存 dict 行为替代数据库/SSE 验收。

## 7. 失败处理、停止条件与回滚

| 场景 | 预期失败方式 | 回滚/恢复原则 |
|---|---|---|
| 缺失、失效或不可验证的 issuer/JWKS/算法配置 | 研究路由返回非成功状态并不读取/创建数据；绝不回退到 `SECRET_KEY`、匿名用户或 Near token。 | 修复机密配置和证书后再启用研究访问；旧新闻/分析/agents 服务不因 F01 变为匿名研究服务。 |
| Evidence 时点倒挂、无许可展示或事实 Claim 无证据 | 拒绝链接/发布事实 Claim；未来执行方应转 `needs_review` 或记录显式未知，不能完成为事实结论。 | 修正源元数据或许可后新增合规 Evidence；不篡改既有审计/事件记录。 |
| 数据库事务、事件或审计持久化失败 | 回滚整个写事务，不发送成功/完成 SSE；客户端可带相同 `request_id` 安全重试。 | 先恢复数据库再重试；若 Run 已创建，幂等读取原 Run，不创建影子运行。 |
| 并发相同 request_id | 唯一键冲突后重读并比较请求指纹；不同指纹返回 409。 | 不以删除原 Run 或重置 seq 解决冲突。 |
| broker/worker 未安装、delivery 未确认或 F03 worker 故障 | outbox 不标记已送达并按退避重试；run 保持 `queued`，或已被 capability claim 后由 F03 以状态机写 `failed/needs_review`；绝不由 F01 伪写 `started/completed`。 | 修复 transport 或部署 F03 的同名 worker 后由 outbox/安全重投递恢复；不复制 bearer 到任务，也不在 F01/F02 中临时执行 Flow。 |
| 迁移或启动失败 | `alembic upgrade head` 非零即阻断服务启动。 | schema 为增量：先将应用回退到上个已知版本；生产环境不得自动 `downgrade`/删除含审计或 run 数据的表。只有经备份、空库验证和人工批准，才允许在隔离环境验证 Alembic downgrade。 |
| 上游 C0、身份传递或数据许可发生不兼容 | 停止实施，不在 F01 中私自新增字段语义或放宽认证。 | 先修订 Parent Plan 的 C0，并同步 A01/F02 的契约 fixture 和评审。 |

## 8. 依赖、交付顺序与未来 PR

1. **实施前置**：父计划 C0 及双方规划 PR 已审阅；部署方已确定 issuer、audience、JWKS 可达性、非对称算法和 `research:create`/`research:read`/实体范围的 claim 口径。当前仓库没有可复用认证实现，缺失这些输入时应停在此计划，不得虚构 auth。
2. **运行依赖**：现有 PostgreSQL 15 开发服务（`deploy/docker-compose.dev.yml:4-19`）、已声明的 Alembic、将新增的 JWT/JWK 验签依赖、现有任务 transport（F01 只适配其可靠投递能力）以及独立测试数据库。Redis、Celery、Milvus、Neo4j 不是 F01 的事件账本替代品；task transport 也不是第二份 run 状态机。
3. **下游依赖**：F02 复用已发布的 `research_auth`、`EvidenceRepositoryPort` 与 `ResearchRunServicePort`（而非研究表/ORM）来**扩展** F01 已注册的 `research.py`，实现 evidence 查询、只读 API/MCP 和 fixtures。F03 在自己的 worker 文件注册 `finnews.research.execute_run.v1`，经 Port capability claim/append/snapshot 写入真正的研究流；它不编辑 F01/F02 shared router。A01 可只消费 C0，不能绕开此处 principal/scope 语义。
4. **未来实施分支/PR**：在 C0 合流后，从 FinnewsHunter 最新 `main` 创建唯一独立分支 `feat/finance-f01-evidence-run`，发起一个标题为 `feat(finance): F01 evidence and research run ledger` 的 PR 到 `main`。PR 只涵盖本计划的文件边界、测试结果、C0 版本和对 F02 的依赖说明；不基于未合并的 A01 工作树，不提交 `AgenticX/`。

## 9. 建议节奏与完成定义

| 时间盒 | 交付检查点 |
|---|---|
| 第 1–2 天 | 确认 C0 与外部身份 claim 口径；建立 Alembic 环境和先失败的 schema 测试；不开始历史 News 回填。 |
| 第 3–5 天 | 完成研究模型、时点/Claim 服务校验、JWT/JWK principal 与审计，跑 PostgreSQL 迁移和权限测试。 |
| 第 6–8 天 | 完成幂等创建、状态机、事件账本、typed Port、outbox dispatch hook 和 SSE `Last-Event-ID` 回放，覆盖并发/失败事务。 |
| 第 9–10 天 | 运行完整 F01 验收、旧路由回归、迁移/启动演练与安全审查；发布 Port/task-name 文档与 fake transport fixture，交付给 F02/F03。 |

**完成定义**：上述六类测试在隔离 PostgreSQL 全绿；所有 F01 研究响应及 public Port 符合 C0 所有权、时点、许可、snapshot、状态、幂等和回放不变量；首次 queued run 的 durable dispatch hook 可由 F03 worker 实际消费，迁移失败会阻断启动；旧 `/news`、`/analysis`、`/agents` 路由仍存在且未被重新解释。完成 F01 也不等于已完成 MCP、实际研究生成、模型评测或 Near 联调。
