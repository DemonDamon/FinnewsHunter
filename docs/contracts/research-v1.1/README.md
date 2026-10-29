# research-v1.1 契约

本目录冻结 FinnewsHunter 的 `research-v1.1` 结构契约。它是后续研究账本、受保护 HTTP 路由和 MCP adapter 的公共输入，不是生产端点、权限实现、来源准入实现或 worker。

## 生成与校验

在仓库根目录使用 S00-B 的隔离环境执行：

```bash
PYTHONPATH=backend /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/contracts-env/bin/python \
  backend/scripts/generate_research_contracts.py
PYTHONPATH=backend /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/contracts-env/bin/python \
  backend/scripts/generate_research_contracts.py --check
PYTHONPATH=backend /Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/contracts-env/bin/python \
  -m pytest -q backend/tests/research/test_contract_schema.py
```

`contracts.py` 是唯一 DTO 源。生成器从其中的具体 Pydantic 模型产出 `schemas/`、`fixtures/` 和 `manifest.json`；不能手工维护第二套 schema。`manifest.json` 中的 `contract_digest` 只哈希其余 manifest payload，避免自引用。所有路径均相对本目录，输出没有生成时间戳或随机 UUID。manifest 的 `mcp_result_policy` 与 `fixtures/mcp-result-policy.json` 同时冻结四种 envelope 状态到 MCP `CallToolResult.isError` 的映射。

## 固定接口 DAG

固定 MCP endpoint 是 `/api/v1/mcp`，只登记以下五个原始工具：

1. `finnews.search_articles`
2. `finnews.get_evidence`
3. `finnews.get_market_snapshot`
4. `finnews.start_research`
5. `finnews.get_run`

每个输出 schema 都绑定实际具体类型的 `ResearchEnvelope[T]`，不使用 `Any`。HTTP 仅登记四个计划路径：创建/读取 run、读取 run events、带 `run_id` 的 evidence 读取；本节点不注册 router。

## 结构校验与运行时校验的边界

JSON Schema 校验类型、长度、正则、UUID/日期格式和额外字段。它无法表达「相对于当前时间不得 future」：`as_of` 由 DTO 的 runtime validator 根据显式 context 的 `now`（生产默认 UTC 当前时间）判断，测试固定为 `2026-10-29T10:05:00+08:00`。同理，timezone 使用 `ZoneInfo` 进行 runtime 验证，naive 时间被 DTO 拒绝。

Pydantic 还校验 Evidence/Market/Brief/Run/Event/Envelope 的结构性关联，例如 market evidence 的 `evidence_id` 一致性、fact 必须至少引用一项 evidence、Brief 的 `as_of` 一致和 completed run 的合法 Brief 读取。`error_code="license_revoked"` 只能出现在 `completed` run，且 `brief` 必须为 `null`；任何其他 `completed` run 都必须有非空 Brief。该保密不变量同时由 Pydantic 和生成 JSON Schema 的 model-level 条件（包括嵌套 `ResearchEnvelope[ResearchRunViewV1]`）拒绝。十进制字段是严格 JSON 字符串；JSON float、科学计数法、NaN、Infinity 和前导零都不被接受。兼容短代码仅在工具输入边界把 `SH600519`、`SZ...` 或 `BJ...` 规范成 canonical ID，DTO 内部和 Evidence 一律要求 `CN.<market>.<six digits>`。

本 C1 只冻结数据结构。principal 身份、scope、实体范围、许可/来源准入、快照冻结、时点可得性、访问时再次许可校验、数值复算、币种/单位语义、执行状态迁移、限流与配额均由后续 S01/S02/S03/S05 实现并强制。`origin=fixture`、`is_mock=true` 和 `example.invalid` 仅可用于离线 fixture；所有生成 fixture envelope 一律使用 `license_status="not_applicable"`，绝不代表真实来源授权、真实市场数据或模型批准。

## MCP result policy

`fixtures/mcp-result-policy.json` 为每种状态给出相同对象的安全 text JSON、`structuredContent` 和 `isError` 标记；text 与 structured 表达必须相等。冻结映射为：

| Envelope `status` | `CallToolResult.isError` | 消费语义 |
| --- | --- | --- |
| `ok` | `false` | 可读的完整业务结果。 |
| `partial` | `false` | 可读的降级业务结果；调用方必须处理 warnings。 |
| `unavailable` | `false` | 可读的业务不可用结果，仍含稳定 `error` 字段和状态；它不是业务成功。 |
| `error` | `true` | 传输/工具错误；安全 text JSON 仍包含稳定 error code。 |

锁定 AGX 的实际结果提取路径会在 `CallToolResult.isError=true` 时先抛出 `ToolError`，不会把 envelope 当作正常返回值读取。因此 adapter 不得发明绕过 SDK 的 envelope 返回路径；`error` fixture 的 text/structured 内容用于审计与传输一致性，AGX 消费者应按 `ToolError` 处理。`unavailable` 则刻意保持 `isError=false`，以便消费者读取受控业务状态和安全原因。`fixtures/negative/mcp-is-error-conflict.json` 仅用于断言拒绝相互矛盾的状态位，绝不属于有效传输形状。

## 与旧 C0 的差异

C1 增加了可生成 manifest 与 digest、固定五工具的具体 envelope 输出、Evidence 的 `evidence_kind/version/source_policy_version/origin`、与 Evidence 关联的 MarketPayload、十进制字符串、Run 读取时内嵌合法 Brief 路径、`license_revoked` 的安全 completed 表示、八种有界 RunEvent payload、market payload 的同 evidence provenance，以及 text JSON、structuredContent、`isError` 的四态等值/映射 fixture。旧 C0 不可自行扩展为另一份客户端 schema。
