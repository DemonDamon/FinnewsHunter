# S01 研究模式启动与验证

Author: Damon Li

现有后端已有最小 research 装配，仍使用 `app.main:app`，没有新增生产服务、客户端或金融网关。研究功能和执行默认关闭；身份、账本、MCP 与 worker 尚未接入，所以 `/readyz` 必须是 503，不能因为进程能启动就称为可研究。

2026-10-29 验收：本机完整研究测试 **61 passed**；Linux/arm64 镜像内非 Compose 回归 **56 passed**，另有真实 SDK Flow/ReAct 切片 **14 passed**。镜像内依赖校验、数据包导入与应用端点冒烟均通过。远端静态分析与独立代码审查已通过；合并状态以 PR #17/#18 为准。

## 安全诊断

宿主 macOS arm64 使用 `backend/requirements-research.lock`；Linux arm64 使用 `backend/requirements-research-linux.lock`。将对应 hash 锁安装到独立 Python 3.12 环境，不要在用户有未提交修改的主目录强行同步。

```bash
./backend/start.sh --mode research --check
```

这只解析 Compose，不启动服务、迁移或 Uvicorn。

```bash
RESEARCH_ENABLED=false RESEARCH_EXECUTION_ENABLED=false \
  UVICORN_BIN=/path/to/venv/bin/uvicorn \
  ./backend/start.sh --mode research --no-services
```

这不启动 Compose 依赖，只启动原应用的研究诊断模式；不提供研究运行接口，不跑旧 `init_db.py`。`--no-services` 只允许研究关闭，不能以跳过服务绕过迁移条件。本轮没有启动这个长期服务，而是在 TestClient 与隔离可执行文件中验证其行为。结束本机诊断可按 Ctrl+C；正式接入仍须按 S03/S07 审查网络暴露与认证。

## 最小依赖与开关

```bash
./backend/start.sh --mode research
```

这是明确启动本地依赖的命令，本轮没有执行。研究 overlay 默认仅原 PostgreSQL 和 Redis。worker 在 `research-worker` profile，图与向量依赖及 beat 均为显式可选 profile。不自动读取用户 backend/.env，没有新增应用入口。

`--with-worker` 用真实解释器读取注册表。S01 的 `worker_modules == ()`，在任何 Docker 调用前拒绝，不创建空 worker。脚本保持 755，参数错误非零退出。

启用研究必须具备迁移配置，迁移失败不得继续启动。S02 尚未实现，不要开启 `RESEARCH_ENABLED=true` 伪造就绪；来源许可与执行器就绪也不能只靠开关。

## Compose 兼容

```bash
docker compose -f deploy/docker-compose.dev.yml \
  -f deploy/docker-compose.research.yml config --format json
```

`!reset` 清除继承 env_file、`!override` 替换依赖，需要 Compose 2.24.4+；本机验证版本为 2.39.2-desktop.1。旧 docker-compose fallback 只适用于 legacy。原服务集合保留；本轮未执行 up/down、删卷或重置数据库。

## 平台专属锁与验证镜像

原 macOS 锁的 SHA-256 保持 `78ae93b400d147f6b6f0eddf741cc482b94eed4aebb231317b4c5e991093f277`。Linux 锁为 `0ef9efd4cafa08ec46c20e79d16c4100d5381c380c27b126382df3db0b0c7203`，152 项；150 个共同包版本不变。Linux 补齐了来源包按平台声明的传递依赖，不通过去 hash 或删除依赖绕过错误。平台差异与重建命令见 [兼容报告](../compatibility/agx-research-baseline.md)。

同一 `deploy/Dockerfile.celery` 的 research 分支实际 COPY 并严格安装 Linux 锁；entrypoint 仅依赖校验后 exec，不在启动时重装浮动 requirements。legacy 默认仍是原 Python 3.11 和原安装策略。

```bash
docker build --platform linux/arm64 \
  --file deploy/Dockerfile.celery \
  --build-arg PYTHON_BASE=public.ecr.aws/docker/library/python@sha256:17b9724493d916f56565c131f389faff2597f46dec6ce09516f95125bc9f519f \
  --build-arg FINNEWS_MODE=research \
  --tag finnews-s01-verify:20261029 .
```

已核实的官方 Python 基础镜像：[ECR Gallery](https://gallery.ecr.aws/docker/library/python)。使用显式构建参数，没有修改用户全局镜像源、代理或现有服务。

本次镜像构建基于代码 `6b200598a3bd637c0ee789b51773157914a6e641`，实际成功用时 175.51 秒。镜像 ID 为 `sha256:5a7a39df0bcdf0d27d61f310e5a51cea5b3d7764a0ff203800c61a2650ef4feb`，Python 3.12.16、Linux/aarch64。镜像未推送 registry，因此没有 RepoDigest；不要混淆 image ID 与基础镜像 manifest digest。

## 已完成的容器内验证

所有容器均 `--rm --network none`，仅挂任务归档源码 read-only，不挂用户 .env、数据或 key。

- `python -m pip check`：无依赖冲突。
- 真实 SDK Flow/ReAct：14 项通过，scripted provider 不调用付费模型。
- 全部非 Compose 研究测试：56 项通过，包括默认 legacy、公开导出、组件生命周期、启动拒绝反例和同步数据库驱动回归。
- 已安装来源包真实导入成功，没有金融网络请求。
- TestClient lifespan 实测 `/health=200`、`/readyz=503`、`/api/v1/debug=404`；旧模型、业务路由、爬取任务和图/向量模块没有加载。

回归测试的默认值用例必须在未覆盖模式的环境执行；研究模式端点则显式传入 research 且关闭两功能开关。首次扩展验收被 QA 全局模式注入干扰的 3 项失败已通过隔离测试环境修正，生产代码和断言未为此改变。

镜像含 dev 依赖，只是 S01 兼容验证镜像，不是最小化或加固后的生产镜像。未验证其他 CPU 架构，也未宣称金融研究 HTTP/MCP、研究账本、身份授权或真实 worker 已完成。

## 本地回归与回滚

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  /path/to/locked-venv/bin/python -m pytest -p no:cacheprovider \
  -q backend/tests/research
```

本机 61 项通过。契约生成检查、新研究代码 Ruff（88 列）、依赖校验与 diff whitespace 通过。旧公开导出顺序不变，不为清理历史 lint 改变业务行为。legacy router stub 只证明装配等价，不是旧业务全量 E2E。

停止选择研究模式即可回到 legacy；两功能默认关闭。本波无领域迁移或数据写入，不需要删库清卷回滚。用户原未提交修改保留，合并不等于部署。下一批从 S02 身份、证据和事务账本开始，仍需独立实施和验收。
