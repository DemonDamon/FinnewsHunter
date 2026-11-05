# S03-B：受保护 HTTP 研究接口与有界事件回放

Planned-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；授权拒绝、SSE游标与错误映射由强推理代码模型复审
Author: Damon Li
Plan-Id: 2026-11-02-finnews-s03b-http-surface
Parent-Plan: .cursor/plans/2026-11-02-finnews-s03-research-surface.plan.md
Status: Local verified; base 2178163aed761b97089c9c6630a0be2e36038f87; 197 targeted tests and static/contract gates PASS; independent review Medium finding closed, no remaining High/Medium.

## 根因与证据
S03总计划4.2冻结四条C1 HTTP路径；S03-A冻结共享服务`ResearchApplicationService`及HTTP身份函数`verify_http_principal`。服务在`execution_enabled=False`时于调用ledger之前返回`DomainError(execution_unavailable)`，事件服务每次固定读取`EVENT_PAGE_SIZE=100`。当前`main.py`尚未由S03-D接线，本子任务必须导出独立APIRouter并以FastAPI dependency覆盖便于独立测试，不能构建全局composition或暗中挂载。

## 范围/所有权
唯一允许新增：`backend/app/api/v1/research.py`、`backend/tests/research/test_research_http.py`、本计划。禁止改动main/config/composition/MCP/service/ports/DTO、旧API、锁或其他既存文件；handoff按用户指定写入工作区`.work/e2e/logs/s03b-handoff.md`。

## 精确实现
1. `backend/app/api/v1/research.py` 定义`router = APIRouter(prefix="/api/v1/research", tags=["research"])`，导出依赖`get_research_service() -> ResearchApplicationService`和`get_identity_verifier() -> IdentityVerifierPort`作为S03-D可覆盖provider；默认provider抛固定配置错误、不读全局state。`get_principal(request: Request, verifier=Depends(...)) -> Principal`仅将`request.scope["headers"]`传给`verify_http_principal(..., clock=UTC-now)`，不读query/cookie/body。文档精确挂接：S03-D执行`app.include_router(research.router)`。
2. 所有请求错误用固定JSON DTO `{code,message,request_id}`及稳定status：identity_invalid=401；scope不足/资源隐藏=404；request_conflict=409；输入验证=422；execution_unavailable/persistence_failed=503；其他固定DomainError映射404或409；意外异常统一500且不暴露异常。错误message取固定字典，绝不回显敏感值。响应DTO以contracts内相同模型校验/序列化。
3. POST `/runs` body严格`StartResearchInput`（DTO额外字段forbid），直接传入`service.start_research(principal=principal, request=request)`，返回`ResearchRunViewV1`。执行关闭由service拒绝，无ledger写。
4. GET `/runs/{id}` 先严格解析UUID，构造`GetRunInput(run_id=id)`并调`get_run`。
5. GET `/evidence/{id}` 要求唯一`run_id` UUID query，构造`GetEvidenceInput(evidence_id,run_id)`并调用`get_evidence`；不暴露preview绕过快照成员授权。
6. GET `/runs/{id}/events` 只接受单个可选`Last-Event-ID`严格UUID；无query可扩大页上限，调用`service.read_events(principal, run_id, after_event_id)`一次。只有当Port page返回next_event_id与游标一致语义时输出该有限页，event按RunEventV1的UUID、固定type、JSON模型数据编码为UTF-8 `id:`, `event:`, `data:`行并空行结束；header设置`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`。无后台任务/无限流。无效或foreign cursor安全拒绝。

## 测试与验收
仅新增`test_research_http.py`，用FastAPI TestClient及dependency_overrides；以本地内存生成RSA-2048 RS256 key/JWKS、固定issuer/audience与测试clock，不联网、不PG/Redis。fake ledger/service记录写调用。覆盖精确4条router path（含method）、缺失/畸形/过期/错误签名bearer，scope/entity denial、额外body字段、malformed run/evidence/query/cursor ID、资源非枚举错误、SSE有限page的id/event/data/续读、foreign cursor、执行禁用时零ledger写与无queued记录、DTO输出投影。

运行固定解释器`/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python`，`PYTHONPATH=backend`，执行新测试、`test_contract_schema.py`、`test_legacy_route_compatibility.py`及相关identity/service测试；ruff check/format --check、py_compile、contracts generator --check、git diff --check。不得commit/push。交接报告列实际DI签名、测试命令/结果、精确四path及S03-D尚未完成include_router接线。

## 排除项
不负责S03-D总app装配、legacy路由/行为、搜索/行情API、MCP、DB构造、任何executor实现；不声称app现已公开挂载。原生EventSource不能自定义Authorization header不属于本阶段保证。
