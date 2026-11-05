# S03-C：受保护 Streamable HTTP MCP 五工具服务

Planned-with: Manus 2.0
Suggested-Impl-Model: MCP生命周期/认证使用强推理代码模型；schema与测试样板可用代码专精中档
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03c-mcp-surface
Parent-Plan: .cursor/plans/2026-11-02-finnews-s03-research-surface.plan.md
Status: Local verified; base 2178163aed761b97089c9c6630a0be2e36038f87; 183 targeted tests and static/contract gates PASS; independent review closed R1/R2 with no remaining High/Medium. Cancellation proof is ASGI task cancellation, not a real network disconnect.

## 根因、输入与实测依据

S03-B已有 HTTP surface，但独立 MCP transport 尚不存在。MCP不能用session id作为身份：SDK的stateful处理会将后续JSON-RPC message送入session task，因此必须在每个 list/call handler 中重新读取当前 `server.request_context.request.scope` 并调用 S03-A 的 `bind_mcp_principal_context(scope, clock=...)`，不得依赖初始化时的上下文或共享主体缓存。

基线中 `backend/app/research/service.py` 的五个方法分别接受 `principal`、对应 `contracts.py` DTO，并以 `envelope=True` 返回 `ResearchEnvelope[...]`；`identity_context.py` 提供 `ResearchTokenVerifier`、`ResearchBearerAuthBackend`、`PrincipalContextMiddleware`、`bind_mcp_principal_context`。`ResearchEnvelope` 的状态与 `MCP_RESULT_POLICY` 明确对应：只有 `error` 为 `isError=true`，`unavailable`、`partial`、`ok` 均为 false。

使用 S03-B相同解释器 `/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python` 实测 `mcp==1.30.0`。Session manager实际位于 `mcp.server.streamable_http_manager.StreamableHTTPSessionManager`，不是 `streamable_http`；构造签名含 `app,event_store,json_response,stateless,security_settings,retry_interval,session_idle_timeout,max_request_body_size,max_sessions`，`run()` 是 async context manager，`handle_request(scope,receive,send)`接收HTTP ASGI请求。`TransportSecuritySettings` 支持 `enable_dns_rebinding_protection,allowed_hosts,allowed_origins`。实现必须依此实测接口，不改锁。

## 唯一文件所有权

本子任务只改/新增：
- `backend/app/mcp/__init__.py`
- `backend/app/mcp/finnews_server.py`
- `backend/tests/research/test_finnews_mcp_server.py`
- 本计划（实施开始前由 `pending/` 移至 `.cursor/plans/` 根目录）
- `/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/e2e/logs/s03c-handoff.md`

严格禁止修改 `main.py`、`composition.py`、`config.py`、HTTP router、Service、identity、Port、DTO、锁文件及任何其他文件。不得commit/push，不连接真实network、DB、Redis。

## 实施设计

在 `finnews_server.py` 提供 `create_finnews_mcp_app(*, service, token_verifier, clock, allowed_hosts, allowed_origins, ...)` 工厂，返回一个明确的 MCP ASGI transport、供父级使用的 lifespan async context manager和安全readiness信息；具体返回值应可由S03-D不改本模块地将 `manager.run()` exactly once 放入 `ResearchComponents.lifespan`，再将ASGI子应用挂载至 `/api/v1/mcp`。本子任务不启动 FastAPI/uvicorn、不自行执行 lifespan、不私存依赖于 `app.state` 的主体。使用 `Server(name=...)` + `StreamableHTTPSessionManager` + 路径 `/` 的 Streamable HTTP ASGI adapter；认证顺序必须为 SDK `AuthenticationMiddleware(backend=ResearchBearerAuthBackend(token_verifier))` → `PrincipalContextMiddleware(clock=...)` → transport。以 `TransportSecuritySettings` 强制明确的非空allowed hosts/origins策略、DNS rebinding protection、请求体上限；Host恶意请求421、Origin不允许403，不许可省略策略默认放行。

只注册五个工具并与 `TOOL_REGISTRY` 一致：`finnews.search_articles`→`SearchArticlesInput`/`ArticlesSearchResult`；`finnews.get_evidence`→`GetEvidenceInput`/`EvidenceV1`；`finnews.get_market_snapshot`→`GetMarketSnapshotInput`/`MarketPayloadV1 | null`（业务服务的空结果按已冻结服务语义错误Envelope）；`finnews.start_research`→`StartResearchInput`/`ResearchRunViewV1`；`finnews.get_run`→`GetRunInput`/`ResearchRunViewV1`。输入JSON schema直接由各 DTO `model_json_schema()`生成，确认根 schema `additionalProperties=false`，不得自写宽松schema。工具handler在每条请求中以当前 `server.request_context.request.scope` 执行 `bind_mcp_principal_context`，用绑定返回的Principal调用同一个注入 `ResearchApplicationService`，并指定 `envelope=True`。无resources/prompts/第六工具。

handler返回正式 `CallToolResult`：`structuredContent`为 `ResearchEnvelope.model_dump(mode="json")`，唯一TextContent的紧凑JSON由完全同一映射序列化；同一次JSON解析必须严格相等；`isError = (status == "error")`，与 `MCP_RESULT_POLICY` 一致；status=partial仍保留warning。输入DTO验证失败与内部意外异常转为固定、无输入回显的安全错误Envelope；不反射bearer、SQL、异常、堆栈。保留S03-A的service错误码和状态。

SDK stateful session owner不得由旧session绑定的主体决定权限。每条HTTP请求依赖外层官方认证重新调用 verifier；每条handler以当前scope主体为准。实现显式session owner绑定至已验证的 `(issuer, subject/client_id)`，并在每条使用既有session的消息上比对当前认证主体；不一致拒绝且不运行工具。不得缓存Principal。允许同一principal重连使用其原session。

## 具体验收门（执行后逐项记录命令/结果）

1. 使用S03-B固定venv确认 `importlib.metadata.version('mcp') == '1.30.0'`；用锁内官方 `mcp.ClientSession` 与 `streamablehttp_client` 对 ASGI test transport执行真实 initialize→tools/list→tools/call transcript。原始工具名集合精确五项，SDK schema严禁额外字段。
2. success与安全domain failure均断言 `CallToolResult.structuredContent` 等于JSON text decode；`isError == (envelope.status == 'error')`；错误文本不含bearer/SQL/traceback/原始输入。
3. missing/invalid token、无scope/entity授权时不触及不当资源；只调用同一ResearchApplicationService。工具跨Principal时不得获得A已授权session主体权限。
4. 使用真实协议让A initialize、list及call并取得session id，再用B bearer复用同session请求；必须拒绝，不调用service；A携原session重连与后续request仍成功。捕获每请求重新鉴权及handler按当前scope绑定Principal的调用记录。
5. 正常Host与无Origin成功；恶意Host 421，未许可Origin 403，非JSON 400，超大body 413；canonical子应用协议路径为 `/`，由S03-D挂载后唯一 `/api/v1/mcp`，不能依赖重定向或 `/mcp` 二级路径。
6. 真实ASGI transcript覆盖 client disconnect/cancel 与manager lifespan context exactly once进入/退出、退出后无后台task；本子任务只验证可管理lifespan工厂，不假装完成FastAPI接线。
7. 同固定解释器运行新增测试及 `test_research_transport_auth.py`、service/contract及相关身份测试；Ruff check、Ruff format --check、py_compile、contract generator `--check`、`git diff --check`通过；依赖锁无变化。

## Out of scope / 停止条件

不接线S03-D、不改research composition/config/main，不创建FastAPI/Uvicorn/端口，不扩展HTTP、不更改DTO/identity/Port/Service、不新增工具/资源/提示。不访问外部网络、PG、Redis，不提交代码。若SDK锁内接口无法满足每请求验证、session-owner隔离、Host/Origin保护、结构化一致Envelope，则停止并在交接记录明确真实复现，不私造认证或降级安全。

## 交接要求

交付 `.work/e2e/logs/s03c-handoff.md`，列工作树/分支/base、实现签名、工具集合、安全语义、精确测试命令和结果、静态检查、实际manager生命周期入口、未完成S03-D FastAPI lifespan/mount接线。无论本子任务代码是否通过，不得声称已对外可用或端到端完成。
