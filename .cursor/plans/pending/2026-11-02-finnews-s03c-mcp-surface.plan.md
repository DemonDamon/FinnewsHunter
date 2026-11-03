# S03-C：受保护 Streamable HTTP MCP 五工具服务

Planned-with: Manus 2.0
Suggested-Impl-Model: MCP生命周期/认证使用强推理代码模型；schema样板可用代码专精快档
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03c-mcp-surface
Parent-Plan: .cursor/plans/pending/2026-11-02-finnews-s03-research-surface.plan.md
Status: Pending; depends on reviewed S03-A service signature.

## Owned files

- 新增 `backend/app/mcp/__init__.py` 和 `backend/app/mcp/finnews_server.py`。
- 新增 `backend/tests/research/test_finnews_mcp_server.py`。
- 本计划与 `.work/e2e/logs/s03c-handoff.md`。
- 锁定`backend/requirements-research.lock`中`mcp==1.30.0`；禁止升级/降级以回避API测试。
- 不得改app.main/composition/config、A服务、HTTP路由、Celery或任何旧Provider。

## 实现方式

先以安装锁内SDK实测low-level `mcp.server.Server`、`StreamableHTTPSessionManager`、`StreamableHTTPASGIApp`、`AuthenticationMiddleware`和`BearerAuthBackend`的具体接口，再编写adapter；不得使用未经验证的示例API。用共享S03-A `ResearchApplicationService`作为全部工具的唯一调用目标。

实现`create_finnews_mcp_app(...)`返回明确ASGI app、`lifespan`与readiness状态；工厂显式传入 `Server(name=...)`、固定tool handlers、外层Bearer token verifier和`TransportSecuritySettings`。`StreamableHTTPSessionManager`只创建一次，`run()`由父composition统一纳入现有FastAPI lifespan一次；禁止启动新的uvicorn/port。SDK自己的transport路径设置成`/`，父层在唯一`/api/v1/mcp`处挂载，不依靠重定向。

只注册精确五个工具名：`finnews.search_articles`→`SearchArticlesInput/ArticlesSearchResult`；`finnews.get_evidence`→`GetEvidenceInput/EvidenceV1`；`finnews.get_market_snapshot`→`GetMarketSnapshotInput/MarketPayloadV1|null`；`finnews.start_research`→`StartResearchInput/ResearchRunViewV1`；`finnews.get_run`→`GetRunInput/ResearchRunViewV1`。JSON schema `additionalProperties=false`，保留契约长度、时间、分页和entity约束；不注册resources、prompts或第六工具。

每请求用RS256本地JWKS验证。token adapter只留下可信issuer、subject/client id、scopes、entity ids、expires_at；不得保留原JWT在SDK AccessToken或日志。调用同一ContextVar Principal到service。session manager的session owner绑定verified stable `(issuer, subject/client_id)`，同一MCP session被另一principal重用必须拒绝；每条HTTP请求仍重新认证，session状态不得替代权限。

结果返回明确 `CallToolResult`：结构化Envelope置`structuredContent`，同一Envelope compact JSON放唯一text content；`isError = status in {error, unavailable}`（需按Master定义实测）；`partial`不是错误但必须有warning；成功不含error。异常只用safe Envelope，不泄露内部异常。

## AC

- 使用锁内官方 `mcp.ClientSession`、`streamablehttp_client` 对 ASGI test transport 做真实`initialize`→`tools/list`→`tools/call`协议往返；list结果严格与五个原始名一致。
- 对成功与失败各验一次：structuredContent严格等于text解析对象；isError与status对应；错误为稳定DTO且无JWT/SQL/堆栈/原文。
- 缺失/无效token、scope/entity不足均失败；session A初始化后以B bearer继续POST必须由SDK session-owner保护拒绝，不能继承A权限或访问B资源；A不能读取非其拥有的run。
- 正确Host和无Origin成功；恶意Host→421、未许可Origin→403、非JSON POST→400、超大body→413；授权适配器不打印header。
- canonical请求直接命中`/api/v1/mcp`；`/api/v1/mcp/mcp`不作为替代成功路径；不发生302/307。
- 测试cancel/disconnect、manager.run恰一次启动/退出、重启使用新manager实例；无后台task残留。
- ruff/format/py_compile/diff-check与现有schema检查通过，不更改依赖锁。

## 风险与停止条件

若锁内SDK不能同时做到每请求验证、session-owner隔离、Host/Origin校验、正确StructuredContent/error且同app挂载，则停止S03-C并报告实际复现；不得私造OAuth issuer、伪造用户claims、关闭session安全、另起生产服务或切换SDK版本。