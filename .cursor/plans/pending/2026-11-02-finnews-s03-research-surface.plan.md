# S03：单一后台入口上的受保护研究 API 与 MCP

Planned-with: Manus 2.0
Suggested-Impl-Model: 简单路由接线用代码专精快档；身份桥、MCP 生命周期及会话隔离用强推理代码模型
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03-research-surface
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Status: Pending; implementation must wait for S02-C final independent review and a clean committed baseline.

## 1. 目的和范围

在现有 `backend/app/main.py:app` 中接入研究域 HTTP 与 MCP surface；不新建金融专用 FastAPI、Uvicorn 进程、端口、身份平台或网关。所有传输最终调用同一个 `ResearchApplicationService`，其唯一持久化边界为 S02 的 `ResearchLedgerPort`、身份边界为 `IdentityVerifierPort` / `AuthorizationPort`。S03 结束时，客户端可在同一权限规则下读取已登记的 Evidence、Market snapshot、Run/Brief 和提交后的事件，并可请求创建 run；如果 S04 executor 未就绪，创建必须返回安全的 `execution_unavailable`，不得留下 queued row。

只接触数据库中已登记且通过当前 SourcePolicy 检查的版本。固定 `as_of` 查询绝不 live-refresh；不新增采集器，不从 legacy `news_v2`/Provider 返回未经登记的正文，不把 fixture 装入公开 app，不调用 LLM。用户已授权的单一官方公告候选只作为后续 S05 真实试点输入；因来源文件记录的存储/再展示/模型使用权仍需合规确认，S03 不下载/持久化/发送其正文。

## 2. 不变量

1. Research mode 与 legacy mode 隔离：`APP_MODE` 默认 `legacy`、`RESEARCH_ENABLED` 默认 false、`RESEARCH_EXECUTION_ENABLED` 默认 false；未启用 research 时四条 HTTP 路径和 `/api/v1/mcp` 均不存在。任何缺失配置都 fail closed。
2. HTTP 严格只有 C1 manifest 中四条路径：`POST /api/v1/research/runs`、`GET /api/v1/research/runs/{id}`、`GET /api/v1/research/runs/{id}/events`、`GET /api/v1/research/evidence/{id}?run_id={id}`。MCP canonical mount 为 `/api/v1/mcp`，只有固定五个原始工具名：`finnews.search_articles`、`finnews.get_evidence`、`finnews.get_market_snapshot`、`finnews.start_research`、`finnews.get_run`。
3. HTTP 与 MCP 复用同一已验证 `Principal`、相同服务实例、相同 Pydantic DTO、相同授权/许可判定；不能在 MCP session、全局 server、共享 `app.state` 或日志中留存可串用户的 bearer/principal。每个请求重新验身份；MCP session ID 不是身份，既有 session 不可由另一个 principal 接管。
4. 用 RS256、本地注入的受信 public JWKS、固定 issuer/audience；不跟随 token 内 `jku`/`x5u`，不在线下载公钥，不接受对称算法。MCP SDK 版本按 research lock 的 `mcp==1.30.0` 验证；不改变锁版本以迁就 API。
5. MCP JSON-RPC 工具错误的 `isError` 与 `ResearchEnvelope.status` 一致；text block JSON 与 `structuredContent` 序列化后相同。Host/Origin、请求大小、输入额外字段均有界。不得暴露 SQL、任意 URL、shell、模型/provider配置、交易、删除或 Evidence 登记工具。
6. events 仅从 C1 已提交 ledger 回放；SSE `id` 是 event UUID，`Last-Event-ID` 必须属于该 run。每次返回有限页并结束，客户端用游标续读；不能凭 Celery、MCP会话或模型 FinalEvent 伪称完成。
7. read service 不实现 SourcePolicy 撤销新语义；S02-C已记录的“事后独立撤销事件”仍为明确后续门禁，不得用新增 policy version 偷偷推断旧版本已撤销。当前所有查询继续走 C1 精确 policy-version/expiry 规则。

## 3. 子计划、所有权与依赖

| 子计划 | 职责 | 唯一文件所有权 | 依赖 |
|---|---|---|---|
| S03-A `2026-11-02-finnews-s03a-domain-service.plan.md` | 统一应用服务、Envelope/错误映射、请求时钟与身份上下文/TokenVerifier桥 | `backend/app/research/service.py`, `backend/app/research/identity_context.py`, 对应 `test_research_service.py`、`test_research_transport_auth.py` | S02-C通过复审并提交；先于B/C |
| S03-B `2026-11-02-finnews-s03b-http-surface.plan.md` | 四条 HTTP 路径、SSE 有界回放与 bearer依赖 | `backend/app/api/v1/research.py`, `test_research_http.py` | A |
| S03-C `2026-11-02-finnews-s03c-mcp-surface.plan.md` | 官方MCP 1.30.0 Streamable HTTP、五工具、会话/Host/Origin安全 | `backend/app/mcp/__init__.py`, `backend/app/mcp/finnews_server.py`, `test_finnews_mcp_server.py` | A |
| S03-D `2026-11-02-finnews-s03d-app-integration.plan.md` | 配置校验、组件装配、唯一FastAPI mount及跨传输集成验收 | `backend/app/core/config.py`, `backend/app/research/composition.py`, `backend/app/main.py`, `test_research_app_boot.py`, `test_research_surface_integration.py` | B/C |

先完成并审阅A，冻结服务签名；之后B/C可在独立工作树并行；最后由父 owner 实施D并作唯一跨层复审。新计划创建时必须先留在 `.cursor/plans/pending/`；启动某子计划前，先将该计划移至 `.cursor/plans/` 根目录并记录精确 commit SHA。不同子计划不得编辑同一文件；发现所有权冲突时停止并重新拆分。

## 4. 逐层行为

### 4.1 应用服务与请求身份

`ResearchApplicationService` 接收显式注入的 `ResearchLedgerPort`、`AuthorizationPort`、UTC-aware clock 和开关；不读取环境、不创建 DB session、不访问网络。它提供五个 MCP 对应的方法及四个 HTTP 领域操作，输入仅为 `contracts.py` 已定义 DTO。它只负责调用冻结 Port、产生 `ResearchEnvelope`（MCP）、将 safe `DomainError` 映射成 `status=error|unavailable` 与稳定 `ContractError`，不得覆盖/绕过 ledger 授权。

传输身份依赖从 `Authorization: Bearer <JWT>` 提取 `BearerCredential` 后调用 `LocalRS256IdentityVerifier`。拒绝缺失、空、超长、重复/格式异常 bearer；错误不得反射输入或写入日志。MCP TokenVerifier adapter 将验证结果映射为官方 SDK `AccessToken` 的安全身份字段（稳定 `client_id`/`subject`、issuer、scopes、过期时间和已验证 entity IDs）；`AccessToken.token` 不能保存原始 bearer。request-local middleware 从已认证 scope 构建 `Principal` 上下文并在 ASGI 完成/异常/取消路径 reset；禁止 global principal、session cache 或以 `client_id` 替代资源授权。

### 4.2 HTTP

在 `backend/app/api/v1/research.py` 注册四条路径，使用严格 C1 DTO；不更改遗留 `/api/v1/news*` 行为。`POST` 只允许 `StartResearchInput` 的字段；身份仅取 bearer；返回 ledger 的 `ResearchRunViewV1`。必须先检查 `RESEARCH_EXECUTION_ENABLED` 和 executor readiness，S04未安装时失败前不写入。`GET run` 返回 ledger 安全投影（含合法 Brief 或撤权后的无 Brief completed 状态）。`GET evidence` 同时传 evidence_id 与 run_id，以快照成员权限为准。events 路由调用 `ResearchLedgerPort.read_events`，解析可选 `Last-Event-ID` UUID，最大页大小取固定服务端上限（不由 query 增大），每个 event 输出 `id:`、固定 `event:`、同一 C1 payload 的 JSON `data:`；成功响应 `text/event-stream` 且有限结束。

### 4.3 MCP 与唯一服务生命周期

在锁定的 `mcp==1.30.0` 下先用实际 SDK API做本机无网契约测试，优先使用 low-level `Server` + `StreamableHTTPSessionManager`，使handler能明确返回 `CallToolResult(isError, content, structuredContent)`；通过 `AuthenticationMiddleware`/SDK bearer backend 在每个 initialize/list/call 请求上运行 token verifier。`StreamableHTTPSessionManager` 必须由 `ResearchComponents.lifespan` 恰好一次 `async with manager.run()` 管理；挂载的子 ASGI app 不得假设它的 lifespan 会被父 FastAPI 自动调用，也不得启动第二个 Uvicorn。

显式把 SDK transport 路由设为 `/`，然后只在 `app.main:app` 的 `/api/v1/mcp` mount；以 HTTP transcript 测试该 canonical path，不得出现 `/api/v1/mcp/mcp`、302/307重定向。配置严格 allowed hosts/origins；不同 principal 尝试沿用已建立 session 必须被拒，合法同 principal 重连按协议工作。工具只接受现成 Input DTO 的 JSON Schema，additionalProperties=false；禁止 resources/prompts及额外工具。

### 4.4 组件与准备度

只在 `APP_MODE=research` 构造 research components；在 `RESEARCH_ENABLED=false` 时不挂路由/MCP。enabled但无 issuer/audience/JWKS、无明确 Host/Origin策略或无 DB配置时，保留 liveness但 readiness对应项为 false，认证/操作不误报成功。S04 executor 未就绪时 start 仍不可成功，但只读工具在其依赖就绪后可用。所有公开诊断返回固定 reason enum，不包含DSN、公钥JSON、bearer、SQL异常或原始第三方内容。

## 5. 验收门

1. 固定解释器下，S03全测试、旧 `test_research_app_boot.py`、旧模式API兼容测试通过；Ruff 88列、Ruff format、`py_compile`、`git diff --check`、research contract generator `--check` 通过；锁文件无变更。
2. 四条 HTTP 路径和五个 MCP工具精确集合；HTTP与MCP对相同 principal/输入/run/evidence得到相同领域结果；拒绝路径无资源枚举；未就绪executor不会写 queued/outbox/quota。
3. 正常 MCP initialize/list/call、无效bearer、scope不足、实体不匹配、无效Host/Origin、跨principal session takeover、客户端取消/ASGI关闭、同一session重连均以官方锁定SDK集成测试验证。
4. FastAPI真实lifespan启动/关闭session manager一次、无泄漏；仅一个 `app.main:app`，端口/服务数量不变；`APP_MODE=legacy` 与 `RESEARCH_ENABLED=false` 不新增对外路由。
5. DB交互使用任务专属真实PostgreSQL测试服务和唯一schema；不连接用户数据库、不用SQLite证明并发/事务。无实际第三方网络、模型调用或真实证券数据调用。
6. 独立只读复审所有High/Medium关闭后才能将S03计划标local verified。服务化代码commit可以分阶段，但未到S04/S05/S06前不得称端到端完成或合并最终PR。

## 6. Out of scope / 风险门

- 不改遗留新闻正文、debug、LLM配置、alpha API；不删除或重写OpenBB/历史provider代码。
- 不新增真实数据采集/抓取或模型适配器；S05才通过AGX Flow接入批准来源与 `glm-5.3-flash`，并且来源授权/第三方模型传输条款仍须先核对。S03只对本地fixture/隔离PG开展测试。
- 不新增事件撤销管理API；SourcePolicy事后撤销语义需在S04/S05真实来源试点前独立关闭。
- 不开公网、不配置部署域名、反向代理、Near Connector、凭据，不启用市场行情、自动交易或后台定时采集。

## 7. 下一步

S02-C最终独立审查通过并形成干净本地commit后，激活S03-A；A的签名经父 owner 冻结后，再并行S03-B/S03-C；两者独立复审和协议测试通过后实施S03-D。