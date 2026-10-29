# S01 研究模式启动与验证

Author: Damon Li

现有后端已有最小 research 装配，仍使用 `app.main:app`，没有新增生产服务、客户端或金融网关。研究功能和执行默认关闭；身份、账本、MCP与worker未接入，所以 `/readyz` 必须是503，不能因为进程能启动就称为可研究。

本地代码门已通过：固定 Python 3.12.12 下 **29 tests passed**。Linux镜像子门仍为 **blocked**，原因和复验命令见下文。

## 安全诊断

从仓库根目录执行，先安装 S00 精确依赖锁到独立环境；不要把用户有未提交改动的主目录当作本波基线。

```bash
./backend/start.sh --mode research --check
```

这只解析Compose，不启动服务、迁移或Uvicorn。

```bash
RESEARCH_ENABLED=false RESEARCH_EXECUTION_ENABLED=false \
  UVICORN_BIN=/path/to/venv/bin/uvicorn \
  ./backend/start.sh --mode research --no-services
```

这不启动任何Compose依赖，只启动原应用的研究诊断模式；不提供研究运行接口，不跑旧 `init_db.py`。`--no-services` 只允许 `RESEARCH_ENABLED=false`，设为true时提前拒绝，不能以跳过服务为由绕过迁移检查。

第二条命令会启动本机Uvicorn，**本轮没有实际启动这个长期服务**，而是在TestClient与fake executable中检查其行为。结束诊断可按Ctrl+C。正式接入前仍须按S03/S07审查网络暴露与认证。

## 最小依赖与开关

```bash
./backend/start.sh --mode research
```

这是将来明确启动本地数据库依赖的动作，**本轮没有运行**。研究overlay默认仅原PostgreSQL和Redis。worker在 `research-worker` profile，Neo4j、Milvus相关服务及beat为显式optional profile。worker不再硬依赖Neo4j，不自动读取用户backend/.env，没有新增MCP/appservice。

`--with-worker` 用真实解释器读取组件注册表。S01的 `worker_modules == ()`，在任何Docker调用前直接报 `no worker modules are registered`，不创建空worker。参数错误非零退出；脚本保持755，支持直接执行。

启用研究必须存在Alembic配置与迁移目录，迁移失败非零退出且不继续应用启动。S02尚未落地，不要开启 `RESEARCH_ENABLED=true` 伪造就绪。实际来源许可与执行器就绪也不能只靠环境开关。

## Compose兼容

```bash
docker compose -f deploy/docker-compose.dev.yml \
  -f deploy/docker-compose.research.yml config --format json
```

overlay用 `!reset`清除继承env_file、`!override`替换依赖，需要Compose 2.24.4+。本机实际为2.39.2-desktop.1。旧docker-compose fallback只适用于legacy；research仍须支持这些tags。

原compose及legacy服务集合保留，未执行 `up/down`、删卷或重置数据库。原文件的version obsolete警告不阻断config，本波未为清理它改动无关文件。

## 锁定验证镜像

同一个 `deploy/Dockerfile.celery` 增加可选research构建：Python3.12、S00完整hash lock、依赖目录 `/opt/finnews-deps`。research entrypoint只 `pip check` 后exec，不启动时重装浮动requirements。legacy默认仍为原Python3.11和原策略。

```bash
docker build --platform linux/arm64 \
  --file deploy/Dockerfile.celery \
  --build-arg PYTHON_BASE=python:3.12 \
  --build-arg FINNEWS_MODE=research \
  --tag finnews-s01-verify:20261029 .
```

S00 lock在macOS arm64/Python3.12.12已完整安装并检查，SHA-256为 `78ae93b400d147f6b6f0eddf741cc482b94eed4aebb231317b4c5e991093f277`。此验证镜像含dev依赖，不是最小化或加固后的正式生产镜像；最终发行仍需S07安全review。

### Linux子门的实际阻塞

Docker Engine 28.4.0为linux/arm64。2026-10-29实际构建在pip安装层之前失败：本机配置的 `hub-mirror.c.163.com` 获取python:3.12 manifest返回EOF。目标镜像没有生成，没有image ID，也没执行容器测试。

本机无缓存python:3.12。对官方registry显式地址的25秒探测超时；经核实的Docker Verified Account ECR Public地址探测也25秒超时。没有修改全局Docker设置、用户代理、现有服务或依赖锁。

Linux `pip check`、真实AGX Flow/ReAct执行和无网络容器应用冒烟全部 **not run**，不能用Compose config或本机29项测试代替。网络恢复后重跑同一hash构建；若锁在Linux不兼容，交回S00处理，不得去hash或改浮动安装。

官方ECR可作为显式build arg候选，但本机未验证可达：[Docker官方Python Gallery](https://gallery.ecr.aws/docker/library/python)；[AWS发行说明](https://aws.amazon.com/blogs/containers/docker-official-images-now-available-on-amazon-elastic-container-registry-public/)。

### 镜像生成后的待执行冒烟

以下不是已完成证据：

```bash
docker run --rm --network none --entrypoint python \
  -e APP_MODE=research -e RESEARCH_ENABLED=false \
  -e RESEARCH_EXECUTION_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/app -v "$PWD/backend:/app:ro" -w /app \
  finnews-s01-verify:20261029 -c 'from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); c.__enter__(); assert c.get("/health").status_code == 200; assert c.get("/readyz").status_code == 503; assert c.get("/api/v1/debug").status_code == 404; c.__exit__(None, None, None)'
```

还须在同一image运行pip check和AGX真实无网Flow/ReAct，记录image digest、Python patch版本与结果。只挂任务源码read-only，不挂用户.env、数据或key；用 `--rm --network none`，不启用金融网络或模型。

## 本地验收和回滚边界

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  /path/to/locked-venv/bin/python -m pytest -p no:cacheprovider \
  -q backend/tests/research
```

实际29 passed，无skip。两脚本bash语法、新研究模块与测试full Ruff、受限生产代码Ruff、pip check和diff whitespace通过。原__all__顺序与main未触及的F841保留，不为清理基线lint改变旧行为。

fake executable只证明控制流；真实解释器空worker反例、TestClient lifespan与sys.modules隔离已分别实测。legacy router stub只证明原prefix/tags/order保持，不是业务E2E。应用接口细节见 [生命周期说明](research-app-lifecycle.md)。

停止选择研究模式即可回到默认legacy及两flag关闭。本波未创建领域表、迁移或数据写入，无需删库清卷回滚。本轮代码以独立PR送审，不自动合main；用户原修改不动。S01整体仍未放行，须先解除Linux子门，再进入S02。
