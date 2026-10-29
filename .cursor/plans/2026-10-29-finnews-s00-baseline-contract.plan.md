# S00：AGX 兼容基线与 research-v1.1 契约冻结

Planned-with: Manus 2.0
Implemented-with: Manus 2.0
Suggested-Impl-Model: 代码专精中档；协议与兼容性由独立强推理审查
Parent-Plan: .cursor/plans/pending/2026-10-29-finnewshunter-agent-first-master.plan.md
Plan-Id: 2026-10-29-finnews-s00-baseline-contract
Status: Locally verified / 2026-10-29 独立复审通过；独立PR送审，未合main
Implementation-Repo: FinnewsHunter
Input-FNH-Commit: 89c50de283d87de07c358b39e8d9e1e1b59eeb55
Input-AGX-Main: ebe368530fb478b8fbfc02e6316da5cbccef1a19
Release-Candidate: v0.6.5 / 0fc089ec6bf0b45f48a7beda06907932ebc98998
Author: Damon Li

Verified-SDK: agenticx[mcp]==0.6.5；官方 MCP 锁定 1.30.0
Verified-C1-Digest: 591d9cdbfc3dbc639cc0859639e11e910ff86a73fdb34c9697ba63af1534a59e
Verified-Evidence: 31 passed（AGX 14 + contract 17）；全 S00 Python Ruff 和 pip check 通过；独立复审 gate=pass
Unverified: Linux/Docker、真实 MCP transport/mount/auth、数据库/worker、合法数据及批准模型；均由后续节点承担

## 1. 本节点完成定义

交付可安装、可实际执行 Flow/ReAct 的精确 AGX 基线；生成 research-v1.1 的可执行 Pydantic DTO、JSON Schema、固定五工具定义、成功/失败 fixture；证明这两项可以在同一干净环境通过测试。将现有 Master 与旧计划关系写进中性架构说明，并记录远端规划 PR #65 的后续处理建议。

本节点不接生产、数据库、供应商或真实模型。不实现 ORM/研究账本、鉴权服务、MCP 生产端点、worker/Flow 业务功能或 Near 新UI。contract 是后续 S02 的公共 DTO 输入，不冒称已实现权限或领域事实核验。

## 2. 证据、根因与改动落点

`backend/requirements.txt:48` 为 `agenticx==0.1.9`，之后只有本地 editable 开发提示；MCP/测试依赖未显式声明。AGX 主线与 v0.6.5 标签不同且 SDK 大量 optional extras 非默认安装，因此 import 成功或 Near UI 有列表不能证明嵌入能力可用。

旧计划只定义文字字段；result_ref 无合法 Brief 读取路径，事件、行情 evidence 与 Decimal 约束不完整，容易跨仓自行发明不同 schema。Master §6 已明确新增 C1 行为，当前任务将它变成可测试契约而非业务实现。

### 独占白名单

S00-A（SDK/依赖）写：
- `backend/requirements.txt`：只改 AGX 精确 pin、清理对应 editable 提示、补显式 MCP dependency，必要且有证据时补缺失 optional 小依赖；不删除遗留需求。
- `backend/requirements-dev.txt`：pytest、pytest-asyncio、jsonschema、ruff、pip 的可兼容范围，不将测试依赖混入生产。
- `backend/requirements-research.lock`：完整 resolved 依赖，记录 Python/平台适用范围；AGX 必须为精确版本或 full40 commit，无 editable/浮动 main。
- `backend/tests/research/test_agx_compatibility.py`、`docs/compatibility/agx-research-baseline.md`、`docs/compatibility/agx-research-baseline.json`。
- 工作环境及中间报告：任务目录 `.work/implementation/sdk-*` 与 `.work/implementation/logs/sdk-*`。

S00-B（契约）写：
- `backend/app/research/__init__.py`、`backend/app/research/contracts.py`；这是 DTO 骨架，不导入 Settings/数据库/AGX。
- `backend/scripts/generate_research_contracts.py`：从 DTO 生成 schema/manifest/fixture 索引，不手写两套模型。
- `docs/contracts/research-v1.1/{manifest.json,README.md,schemas/*.json,fixtures/*.json}`。
- `backend/tests/research/{__init__.py,test_contract_schema.py}`。
- 中间环境 `.work/implementation/contracts-env` 与日志 `contracts-*`。

父 agent 写：Master 状态、S00 plan 状态、`docs/architecture/agent-first.md`、执行索引与第一批进度；不与子 agent 同时写依赖/DTO。

禁止写：用户原 checkout、AGX 主工作树、旧 News/Stock/analysis/alpha、main/config/celery/compose、真实凭据/全局配置、生产库。两个子 agent 不可修改对方拥有的文件，也不可 git commit/push/merge。

## 3. S00-A：SDK 精确基线与兼容测试

### FR-A1 候选与安装

优先真实尝试 `agenticx==0.6.5` 发布物。若索引没有该版本或能力测试失败，保留完整证据，改为 `agenticx @ git+https://github.com/DemonDamon/AgenticX.git@<full40>` 的已审阅不可变提交。先考虑 release tag source commit；只有 tag 缺必要能力才尝试当前主线 full40。禁止直接用用户工作树 editable 或把 SDK 文件复制进 FNH。

Python 使用已安装 3.12.12 干净 venv，依赖安装用 uv，uv cache 尽量指向任务目录。先生成完整 lock，再在第二个干净环境按 lock 安装并 `python -m pip check`。源码 direct URL 必须记录解析 source commit；PyPI 版记录 distribution metadata、下载来源和 hash。不要把 distribution version 0.6.5 当作 source SHA。

`requirements-research.lock` 如果 platform-specific，顶端明确当前已验证平台是 macOS arm64/Python3.12；不得声称 Docker/Linux 已验证。优先 uv pip compile 的通用可移植锁；Git 源下载按 commit，不依赖 tag 可移动性。以后 S01 的镜像验证仍是额外 gate。

### FR-A2 实际调用测试

测试使用 AGX 的真实 `BaseLLMProvider/LLMResponse` 构建无网 scripted provider、真实 `BaseTool`，不可 monkeypatch 出假的 Flow/ReAct 实现：

```text
async Flow.start → listen increments typed state → await kickoff_async() → assert state
scripted LLM first emits FC call to read_snapshot("fixture-id")
real BaseTool._run returns bounded JSON
scripted LLM second emits final content
async for ReActAgent.astream(query) → ToolCallEvent/ToolResultEvent/FinalEvent
await a separate ReActAgent.arun(query) → equivalent successful output
```

构造两次独立 scripted provider，避免 arun 使用已消耗队列。至少覆盖未知工具/不合法参数时没有真实读取、max_iterations 生效、不依赖不存在的 Flow.arun。明确不将 ReAct FinalEvent 当作领域完成。

MCP 兼容测试用官方 SDK 类型构造 CallToolResult，使 text block 的 JSON 和 structuredContent 等价；用现有 MCPHub.extract_tool_result/RemoteTool 提取路径中的实际接口验证（无需网络端点），不手写假的优先级。正式 endpoint/mount/身份测试属于 S03。

### AC-A

1. 干净 environment 安装和 pip check 通过，记录 lock 与实测安装命令。
2. test_agx_compatibility.py 至少 happy/unknown-tool/iteration-cap/Flow async/MCP text-structured 五类断言，实际执行，无真实 API key 或 provider 网络调用。
3. 发布候选失败时报告原始错误摘要与选择下一候选原因；不因 fail 就悄悄 skip capability suite。
4. requirements、lock、报告里的 AGX URL/version/commit 一致；无浮动 main/editable。
5. 后续在统一 environment 运行 contract suite 不冲突。

## 4. S00-B：严格、可生成的契约

### FR-B1 共同类型约定

所有 DTO `extra="forbid"`。required-but-nullable 字段用无 default 的 `T | None`；不要因允许 null 就让客户端省略字段。列表有明确 max_length；拒绝 NaN/Infinity。导入只用 absolute imports，英文 comments/docstrings、模块头 `Author: Damon Li`。

IDs 为 UUID JSON string。单证券 canonical pattern `^CN\.(SH|SZ|BJ)\.[0-9]{6}$`，一处边界规范化 `^(SH|SZ|BJ)[0-9]{6}$`，不能猜公司名。entity_ids 长度1。AwareDatetime 不接受无offset；timezone 使用 ZoneInfo验证。Decimal value 使用字符串正则 `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`，不得接受 JSON float、scientific notation、NaN、leading-zero。confidence 是有限0–1数。UUID/timezone/finite 校验也要在 tests 验证，不只凭 JSON Schema format annotation。

工具输入 as_of 使用验证context中的固定now；生产默认UTC now。test固定2026-10-29T10:05:00+08:00，拒绝future不挪时间。Schema不可能表达“相对当前时刻”条件，README明确其为runtime validator。

### FR-B2 DTO 字段

必须实现以下公开类型；字段列表来自 Master，详细形态如下作为第一版冻结细则：

- `ContractError`：code非空安全slug、message非空最大512、retryable bool。
- `SourceRefV1`：source_id非空最大128、evidence_id UUID、provider非空最大128、version非空最大128、hash 64位小写hex。
- `EvidenceV1`：Master §6.2所有字段；source_url只允许https（test用example.invalid）；excerpt最大4000；license_scope enum `redisplay|metadata_only|no_redisplay|unknown`；quality_status enum按Master；evidence_kind event|market；version/source_policy_version必填；origin live|fixture。Evidence DTO允许incomplete/rejected表示元数据，但准入属于S02，不声称DTO通过就可研究。fetched_at不得早于available_at；published_at不得晚于available_at。market payload单独可选关联，market时必填且evidence_id必须一致。
- `MarketFieldV1`：name非空最大64、value DecimalString、unit非空最大32。
- `MarketPayloadV1`：Master §6.4所有字段；symbol canonical、currency三位大写字母（金融白名单留S02）、adjustment `none|forward|backward`、fields长度1–32、provider/version、is_mock bool。时间有offset；available_at<=fetched_at；不能仅凭正则证明真实币种/许可。
- `NumericAssertionV1`：Master §6.5字段；formula_id identity|percent_change|unit_scale；operand_refs为Evidence+field引用列表最大4；rounding整数0–8。这里只结构检查，复算/币种口径在S05。
- `ClaimV1`：Master §6.5字段；text 1–4000、evidence_ids长度0–20且去重；fact不能为空；as_of aware；valid_until为required nullable且若非空>=as_of；confidence有限0–1；numeric_assertions默认空列表（内部可选增补）。不得凭text正则检查事实正确。
- `ModelTraceEntryV1`：role `draft|review`、provider/model_id/prompt_version/policy_version/eval_version/eval_digest、fallback_reason(required nullable)。只存结构元数据；不含raw prompt/reasoning/secret。model_trace长度0–4，fixture明确fake模型。
- `ResearchBriefV1`：Master §6.5字段；claims最大64；counterarguments为ClaimV1列表最大32；unknowns/limitations字符串列表最大32，每串最大2000；model_trace为上述条目。所有Claim.as_of==Brief.as_of。
- `ResearchRunViewV1`：Master §6.6所有字段；principal_id UUID；status全6种；created_at/updated_at aware且updated>=created；model_id/result_ref/error_code required nullable；prompt_version/policy_version必填；brief required nullable，非空时run_id/as_of匹配。completed必须有Brief，唯一例外是error_code=license_revoked时brief可null；其他状态不得伪装有完整成功brief。
- `RunEventV1`：Master字段；seq>=1；type固定8种；payload用类型映射：started(空或安全dispatch标识)、step_started(step_name)、evidence_added(evidence_id)、claim_checked(claim_id,passed,error_code可null)、needs_review(code)、completed(result_ref)、failed(code)、cancelled(reason)。payload不接受任意dict/unbounded文本，不放stack或模型原文。
- `ResearchEnvelope[T]`：Master共同字段；status固定4种；source最大20；warnings最大20且每串最大512；license_status `approved|restricted|unknown|revoked|not_applicable`。ok必须error=null且data非null；error/unavailable必须error非null，unavailable可以带安全状态data；partial允许安全部分data但必须非空warnings且error可null。对于schema校验不能依赖泛型T=Any的无限数据，五工具使用明确T。

HTTP只登记Master四条路径和形态，MCP endpoint固定/api/v1/mcp。没有创建任何production router。

### FR-B3 五工具输入和输出

五个原始工具名 exact match Master。不增加method。Tool discovery中的inputSchema来自对应Pydantic model。输入例：
- SearchArticlesInput(query 1–256,entity_ids单元素,as_of,limit默认10范围1–20,cursor optional opaque最大512)。Output为ArticlesSearchResult(articles Evidence列表最大20,next_cursor required nullable,truncated bool)，再包ResearchEnvelope。
- GetEvidenceInput(evidence_id,run_id)，Output Evidence。
- GetMarketSnapshotInput(entity_ids单元素,as_of,run_id optional)，Output MarketPayload。
- StartResearchInput(request_id,entity_ids,as_of,seed_evidence_id,question optional最大2000)，Output ResearchRunView。
- GetRunInput(run_id)，Output ResearchRunView。

固定额外字段拒绝provider/model/arbitrary_url/tool_list/principal_id。不可让cursor承载任意URL。opaque cursor仅接受urlsafe base64样式字符，允许末尾=但不执行解析取得网络路径。

### FR-B4 生成和fixture

生成脚本从contracts中的工具registry/schema类型生成：schemas/*.json、manifest.json。manifest字段schema_version、mcp_endpoint、tools(name/input_schema/output_schema)、http_paths、schema_files(path,sha256)、fixture_files(path,sha256)、contract_digest（哈希只覆盖前面payload，禁止自循环）。路径为相对contracts目录路径，不能绝对path。

只输出固定内容；不要每次写当前timestamp导致digest变化。提供 `--check` 只比对生成内容、差异非零退出。fixture由生成脚本的固定canonical示例或schema验证的固定源生成，无随机uuid/time。

至少fixture：合法event/market、queued/completed/license_revoked RunView、五工具成功envelope、unavailable market、error envelope、未来as_of输入、naive time输入、额外model输入、坏numeric/claim/missing-required字段。非法fixture写入negative/并登记expected validation code；不得混进合法schema pass列表。

README给版本/DAG、与旧C0差异、schema-vs-runtime边界、生成/测试命令。fixture source URL为example.invalid且origin=fixture；不能“真实数据授权”或real model approval。

### AC-B

`backend/tests/research/test_contract_schema.py` 实测：
1. 生成/check deterministic；manifest hash与每个文件一致；tools五个、http四个、路径固定；没有secret literal。
2. 正例同时通过Pydantic和JSONSchema(with FormatChecker)，负例拒绝；特别验证future context、naive datetime、extra字段、Decimal float/NaN、fact无citation、Brief/run_id/as_of冲突、missing required nullable、too many entities。
3. 文本与structured fixture相等；已完成run可以完整读取Brief；许可撤销状态不改completed且brief可以null。
4. 不import Settings、数据库、Provider/alpha；不注册路由/生产服务；无网络。
5. C1只冻结结构，README明确principal/许可/snapshot/fence/数值语义由后续节点强制实现。

## 5. 合流、审查和下一节点 gate

两个实现并行，各自独立环境，不能同时pip install同一个venv。S00-A完成后父agent使用其稳定环境同时跑A/B suite；先完成规格与安全审查，再把C1状态从candidate变为frozen。Reviewer只写 `.work/implementation/logs/s00-review.md`，不改实现文件；有问题返回具体文件行和最小修复。

若任何能力或安装不可验证，S00标blocked/partial，不能启动S01实现。修复已知失败后重跑并独立复核。通过后拆S01与S02，但只先执行S01，S02必须消费S01装配hook与S00已冻结contracts。

本轮没有commit元数据确认则保留未提交改动与工作树，不自动push/merge。用户主目录patch在执行前后必须一致。最终报告列明commands、真实tests counts、已验证平台、未验证事项与下一批输入。
