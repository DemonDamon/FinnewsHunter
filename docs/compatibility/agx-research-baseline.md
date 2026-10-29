# AGX research SDK 兼容基线（S00-A）

- 状态：**通过（macOS arm64 / CPython 3.12.12）**
- 作者：Damon Li
- 基线日期：2026-10-29
- 本次 F4 更新：真实 `CallToolResult.isError` 错误路径、C1 四态 fixture 与统一环境联跑已复验。
- 范围：仅验证 FinnewsHunter 后续 research 实现所需的 AGX `Flow`、异步 `ReActAgent`、MCP 结果提取与可复现 Python 依赖；不接入 FinnewsHunter app、数据库、worker、真实 MCP 端点、真实金融来源或模型。

## 结论与锁定来源

首选发布候选 `agenticx==0.6.5` 可从 PyPI 成功安装并通过全部能力测试，因此不需要回退到 Git tag source 或 AGX main。生产依赖固定为 `agenticx[mcp]==0.6.5`，同时显式声明 `mcp>=1.0.0,<2`；完整解析锁将 MCP 固定为 `mcp==1.30.0`。

| 项目 | 实测值 |
| --- | --- |
| 选定 SDK 来源 | PyPI release distribution `agenticx==0.6.5` |
| 实际下载 artifact | `agenticx-0.6.5-py3-none-any.whl` |
| artifact SHA-256 | `45418a80b1142f2e3fdabf9f65882ce8235c649c6602c1b8ad47736d6f1145c9` |
| 实际 artifact 下载地址 | `https://mirrors.aliyun.com/pypi/packages/10/c7/3bd0de2b971df1ba48099cee2480ef2dc6593f50068834128e8e130a5074/agenticx-0.6.5-py3-none-any.whl` |
| distribution metadata | `Name: agenticx`、`Version: 0.6.5`、`Requires-Python: >=3.10`、无 `direct_url.json` |
| lock 中 AgenticX hashes | wheel hash 如上；另含 source distribution hash `18d88b04e3e04d4800db16c036f20538e54bc20dcf4189e43edb92c32a5a678f` |
| Git source fallback | 未使用；无 editable、无浮动 branch、无 `git+` 依赖 |
| 未选择的 AGX source | release tag source commit `0fc089ec6bf0b45f48a7beda06907932ebc98998` 与 main `ebe368530fb478b8fbfc02e6316da5cbccef1a19` 均未作为依赖，因为已验证 PyPI release 足够 |

`backend/requirements-research.lock` 包含 151 个直接或传递解析项及每个 artifact hash（完整文件 309,410 bytes）。其顶部明确：**已验证 macOS arm64 (`aarch64-apple-darwin`) / CPython 3.12.12；Linux 与 Docker 未验证，仍是 S01 gate。** 第二次使用相同输入和选项重新编译后，锁 payload 完全相同（309,211 bytes）。

## 已核对的真实 SDK 接口

本基线在已安装 release 的源码和运行时签名上确认了下列接口，而不是根据计划猜测 API：

- `agenticx.flow.Flow.kickoff_async(inputs=None)`，以及 `@start()` / `@listen(...)`。
- `agenticx.agents.react_agent_async.ReActAgent` 的异步 `astream(query)` 与 `arun(query)`。
- `agenticx.llms.base.BaseLLMProvider`、`agenticx.llms.response.LLMResponse`、`agenticx.tools.base.BaseTool`。
- `agenticx.tools.mcp_hub.MCPHub.extract_tool_result(routed_name, result)`。
- `agenticx.tools.base.ToolError`，以及官方 `mcp.types.CallToolResult`、`TextContent`；已安装 MCP 版本为 1.30.0。

锁定 SDK 的 `MCPHub.extract_tool_result` 真实优先级为：`isError=true` 时先收集非空 text block 并抛出 `ToolError`；只有非错误结果才返回第一个 text/blob content，之后才回退 `structuredContent`，最后才返回原对象。该行为通过安装的 SDK 实际调用确认，而非 monkeypatch 或手写优先级。

## C1 F4：冻结映射与真实错误路径

`backend/tests/research/test_agx_compatibility.py` 直接读取 `docs/contracts/research-v1.1/manifest.json` 和已登记的 `fixtures/mcp-result-policy.json`。测试先断言 manifest 的 `mcp_result_policy` 与 fixture 的全部四态 `isError` 位完全相同、fixture 已登记、text JSON 与 structured 对象相等，再用官方 `CallToolResult` 调用真实 `MCPHub.extract_tool_result`。

| C1 envelope `status` | 冻结 `CallToolResult.isError` | 实测 AGX 消费行为 |
| --- | --- | --- |
| `ok` | `false` | text JSON 被返回为字符串，或结构化结果被返回为对象；两条实际路径解析后都与 fixture envelope 相等。 |
| `partial` | `false` | 同样可读，但调用方必须处理 envelope 的 `warnings`，不可当成完整成功。 |
| `unavailable` | `false` | 同样可读，且保留稳定 `error` 与状态；它是业务不可用，绝非业务成功。 |
| `error` | `true` | SDK 在读取正常返回前真实抛出 `ToolError`；text JSON 与 `structuredContent` 同时存在时，异常消息从 text 形成。测试断言安全消息含稳定码 `execution_unavailable` 和 fixture 的安全 message；另有 structured-only 官方对象测试，仍真实抛出 `ToolError("Unknown error")`，绝不返回 structured envelope。 |

非错误三种状态分别实际覆盖 text 路径和仅 `structuredContent` 路径（共 6 个参数化测试）。`error` 一次使用真实官方对象携带两种同值表示并断言稳定安全码，另一次使用 `structuredContent`-only 官方对象并断言真实 `ToolError("Unknown error")`；两条路径均确认 AGX 不会伪造一个可读 envelope 返回路径。由于 SDK 的错误分支先于结构化提取，调用方收到的是 `ToolError`，不是 structured envelope；这也要求生产 adapter 在 `error` 时始终发送含安全稳定码的 text JSON。

### 后续 S03 adapter 的强制要求

本测试冻结 SDK 消费语义，**不实现或声称实现 transport**。S03 的实际 MCP adapter/mount 必须：

1. 从 C1 manifest 的 `mcp_result_policy` 原样设置 `CallToolResult.isError`；不得为让 AGX 返回 body 而把 `error` 降级为 `false`，也不得把 `unavailable` 升级为 transport error。
2. 对每个返回值生成语义相等的安全 text JSON 与 `structuredContent`；特别是 `error` 的 text 必须保留稳定安全 error code，因为锁定 SDK 的 `ToolError` 消息来自 text，而不是 structured 内容。
3. 让 `partial`、`unavailable` 的调用方显式处理 envelope `status`、`warnings` 和安全 `error`，不把它们宣传为完整成功。
4. 在真实同进程 FastAPI `/api/v1/mcp` mount 上验证 RemoteTool/transport、鉴权、session 生命周期、Origin/Host 和取消行为；本 S00 测试不启动端点，也不覆盖上述项目。

## 实际测试

统一测试解释器的绝对路径：

```text
/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python
```

最终实际命令及结果已保存至 `.work/implementation/logs/s00-fix-sdk.log`：

```bash
PYTHON=/Users/damon/Documents/Manus/2026-10-29/tKG7Sl/.work/implementation/FinnewsHunter/.work/implementation/sdk-clean-065/venv/bin/python

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend "$PYTHON" \
  backend/scripts/generate_research_contracts.py --check
# research-v1.1 contract artifacts are current

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend "$PYTHON" \
  -m pytest -p no:cacheprovider -q backend/tests/research/test_contract_schema.py
# 17 passed in 0.26s

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" \
  -m pytest -p no:cacheprovider -q backend/tests/research/test_agx_compatibility.py
# 14 passed in 1.75s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend "$PYTHON" \
  -m pytest -p no:cacheprovider -q backend/tests/research
# 31 passed in 1.42s

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m ruff check --no-cache \
  backend/app/research backend/scripts/generate_research_contracts.py backend/tests/research
# All checks passed!

"$PYTHON" -m pip check
# No broken requirements found.
```

AGX compatibility suite 的 **14 项**实际测试覆盖：

1. 异步 `Flow.kickoff_async()` 的 start → listener 状态推进。
2. script provider 首次发出 `read_snapshot("fixture-id")` function call，真实 `BaseTool._run` 返回有界 fixture JSON，`ReActAgent.astream()` 产生 `ToolCallEvent`、`ToolResultEvent`、`FinalEvent`。
3. 使用**另一套**未消耗的 scripted provider 和另一个 `ReActAgent` 的 `arun()` 聚合结果。
4. 未知工具名不会读取 fixture。
5. 不合法参数不会读取 fixture。
6. `max_iterations` 返回失败的 `FinalEvent`，而不是继续调用 provider。
7. C1 `ok` 的 text 与 structured 两条真实提取路径。
8. C1 `partial` 的 text 与 structured 两条真实提取路径。
9. C1 `unavailable` 的 text 与 structured 两条真实提取路径。
10. C1 `error` 使用同时携带相等 text/structured 的官方 `CallToolResult(isError=True)` 时真实抛出 `ToolError`，并保留稳定安全错误码。
11. C1 `error` 使用 `structuredContent`-only 的官方 `CallToolResult(isError=True)` 时仍真实抛出 `ToolError("Unknown error")`，不能绕过 SDK 的错误路径。

测试只导入 SDK、Pydantic、pytest、官方 MCP 类型及只读 C1 JSON；不导入 `app.main`、不调用网络或 API key，亦不启动数据库、worker 或 MCP server。`FinalEvent` 仅表示 ReAct 循环结束，**不**被解释为金融领域 research run 已完成。

## 独立复跑

从 FinnewsHunter 隔离 worktree 根目录执行。以下命令始终创建新的任务目录环境，不会安装到全局 Python：

```bash
PYTHON312=/Users/damon/.local/bin/python3.12
UV=/Users/damon/.local/bin/uv
VERIFY_DIR=.work/implementation/sdk-followup-verify
export UV_CACHE_DIR="$PWD/.work/implementation/sdk-cache/uv-cache"

"$UV" venv "$VERIFY_DIR/venv" --python "$PYTHON312"
"$UV" pip sync --python "$VERIFY_DIR/venv/bin/python" --require-hashes --strict \
  backend/requirements-research.lock
"$VERIFY_DIR/venv/bin/python" -m pip check
PYTHONDONTWRITEBYTECODE=1 "$VERIFY_DIR/venv/bin/python" -m pytest \
  -p no:cacheprovider -q backend/tests/research
PYTHONDONTWRITEBYTECODE=1 "$VERIFY_DIR/venv/bin/python" -m ruff check --no-cache \
  backend/app/research backend/scripts/generate_research_contracts.py backend/tests/research
```

生成 lock 的精确命令如下；第二次相同命令的 payload 比较已通过：

```bash
uv pip compile \
  --python /Users/damon/.local/bin/python3.12 \
  --python-platform aarch64-apple-darwin \
  --generate-hashes \
  --no-strip-extras \
  --custom-compile-command 'uv pip compile --python /Users/damon/.local/bin/python3.12 --python-platform aarch64-apple-darwin --generate-hashes --no-strip-extras backend/requirements.txt backend/requirements-dev.txt' \
  --output-file backend/requirements-research.lock \
  backend/requirements.txt backend/requirements-dev.txt
```

## 边界、已知限制与后续 gate

- 已验证平台为 macOS 15.6.1 arm64 / CPython 3.12.12 / uv 0.9.26；没有验证 Linux、Docker 或镜像构建。
- 未启动 FastAPI、FinnewsHunter `app.main`、Celery、broker、数据库、真实 MCP server 或任何金融采集；这不是生产 endpoint/mount/worker 验证。
- 未调用真实或付费 LLM；scripted provider 仅在内存返回 `LLMResponse`。
- S03 仍须在真实同一 FastAPI app mount 上验证并实现 C1 F4 adapter 映射、RemoteTool/transport、请求级鉴权、session lifecycle、Origin/Host 和取消行为。
- S01 仍须在 Linux/Docker 环境独立验证依赖与镜像。
- 当前 uv 0.9.26 没有 `uv pip download` 或 `uv pip index` 子命令；原始错误已保留在 `sdk-pypi-download-0.6.5.log` 和 `sdk-pypi-index-versions.log`。依赖安装、compile 与 sync 均使用 uv；仅为记录实际 wheel filename/hash 而以隔离环境的 `pip download --no-deps` 下载，不安装全局包。

任务日志位于 `.work/implementation/logs/sdk-*`，本次修复与统一环境复验的实际输出位于 `.work/implementation/logs/s00-fix-sdk.log`。它们为真实运行证据，不属于交付文件。S00-A 没有功能性阻塞项，也不宣称实际 MCP transport 已实现。
