# S03-B：受保护 HTTP 研究接口与有界事件回放

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精快档；授权与事件游标由代码专精中档复审
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03b-http-surface
Parent-Plan: .cursor/plans/pending/2026-11-02-finnews-s03-research-surface.plan.md
Status: Pending; depends on reviewed S03-A service signature.

## Owned files

- 新增 `backend/app/api/v1/research.py`：唯一新增HTTP Router，仅四条C1路径。
- 新增 `backend/tests/research/test_research_http.py`。
- 本计划与 `.work/e2e/logs/s03b-handoff.md`。
- 不得修改DTO/Port、identity middleware/service、`api/v1/__init__.py`、composition/main/config、MCP或旧news/router/provider。

## 精确接口

路由使用注入的 `ResearchApplicationService` 与 `IdentityVerifierPort` dependency；每次请求验证bearer，禁止token query/cookie/body fallback。响应模型是 `ResearchRunViewV1`、`EvidenceV1` 或 `text/event-stream`；HTTP不包MCP envelope。

1. `POST /api/v1/research/runs`：严格`StartResearchInput`，额外字段拒绝；principal只来自bearer。执行开关未开或executor未ready时必须在持久化前返回 safe 503/409 对应`execution_unavailable`，禁止run/outbox/quota部分写入。成功返回 ledger 的 `ResearchRunViewV1`；request_id重复异参为409。
2. `GET /api/v1/research/runs/{id}`：UUID路径；授权后返回RunView；completed brief由ledger本地投影；过期/撤权时保留completed并隐藏受限Brief，不读`result_ref`外部URL。
3. `GET /api/v1/research/evidence/{id}?run_id={id}`：两个UUID均必需，ledger必须确认该Evidence是此principal该run的frozen snapshot成员，不能因搜索预览而放宽。
4. `GET /api/v1/research/runs/{id}/events`：可选`Last-Event-ID`头（严格UUID）和只可收窄、不可扩大固定上限的`limit`（默认/最大20）。调用ledger.read_events一次形成有界页，核验游标属于此run。每事件按C1 event UUID输出`id:`, 固定type作`event:`, 以及合法RunEventV1 JSON作`data:`；有限EOF，支持后续Last-Event-ID续读，不无限轮询。

使用一致safe error mapper：401身份无效、403 scope不足（资源不存在与无权的差异按冻结非枚举DomainError映射）、404/409/422/503只返回稳定code、safe message、request_id，不回显JWT、query、原文、SQL或堆栈。不要覆盖research mode顶层错误处理中间件。

## AC

- 用FastAPI `TestClient`/dependency overrides验证路径集合精确4条；默认legacy与research disabled都404；开启模式挂载但无公钥配置时fail closed。
- 缺失/无效bearer、scope不足、entity范围不包含、他人run/evidence/event和foreign Last-Event-ID均拒绝且不透露资源存在性。
- 运行真实PostgreSQL回归：executor not-ready请求后run/outbox/quota/audit无新增写；已有同request id同hash返回同run；异hash409。
- SSE用两个递增seq和续读ID验证事件id、event、JSON data一致，foreign cursor拒绝；测试客户端断开时无后台轮询/任务泄漏。
- 不新增第五条HTTP路径，不把search或market query暴露为HTTP；不读取legacy News正文。
- 固定研究解释器运行新测试、既有API legacy兼容测试、ruff/format/py_compile/diff-check，合同manifest不漂移。

## 验收边界

实现可在S03-D完成挂载后验证；本子计划不得自行改app.main或新启Uvicorn。人工SSE客户端可设置Authorization header；不保证原生浏览器EventSource支持自定义bearer头。