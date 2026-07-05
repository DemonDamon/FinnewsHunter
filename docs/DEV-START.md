# FinnewsHunter 本地开发启动指南

> **目标**：用 **3 条命令** 跑起完整服务，不再分散启动 Docker / Celery / 前后端。

---

## 架构一览

```
┌─────────────────────────────────────────────────────────┐
│  Docker（一条 compose 命令统一管理）                      │
│  ├─ Postgres :5433                                      │
│  ├─ Redis    :6380                                      │
│  ├─ Milvus   :19530                                     │
│  ├─ Neo4j    :7474 / :7687                              │
│  ├─ Celery Worker  ← 定向爬取 / 定时任务 必须             │
│  └─ Celery Beat                                       │
├─────────────────────────────────────────────────────────┤
│  本地进程（热重载，dev-up 自动后台启动）                    │
│  ├─ FastAPI  :8000                                      │
│  └─ Vite     :3000                                      │
└─────────────────────────────────────────────────────────┘
```

**为什么 Celery 放 Docker、API 放本地？**
- Celery 依赖与中间件在同一 Docker 网络，连接 `postgres:5432` / `redis:6379` 更稳定
- FastAPI / 前端本地跑，改代码即时生效，无需 rebuild 镜像

---

## 三条命令

### 命令 1：首次准备（换机 / 新 clone 后执行一次）

```bash
cd examples/agenticx-for-finance/FinnewsHunter
bash scripts/dev-prepare.sh
```

会做：
1. 检查 Docker
2. `pip install` 后端依赖
3. `npm install` 前端依赖（若无 node_modules）
4. 复制 `backend/env.example` → `.env`（若不存在）
5. 启动中间件并 `init_db.py`

**⚠️ 准备完成后务必编辑 `backend/.env`，填入 LLM API Key**（如 `DASHSCOPE_API_KEY`）。

---

### 命令 2：每次开发启动

```bash
bash scripts/dev-up.sh
```

会做：
1. **Docker 一次拉起全部**：Postgres / Redis / Milvus / Neo4j / **Celery Worker / Celery Beat**
2. 本地后台启动 FastAPI `:8000`
3. 本地后台启动 Vite `:3000`

访问：
- 前端 http://localhost:3000
- API 文档 http://localhost:8000/docs

---

### 命令 3：查看状态 / 停止

```bash
# 查看所有组件是否在线（重点看 celery_worker 是否为 running）
bash scripts/dev-status.sh

# 停止本地 API + 前端（Docker 保留，下次启动更快）
bash scripts/dev-down.sh

# 停止全部（含 Docker 容器）
bash scripts/dev-down.sh --all
```

---

## 数据备份 / 迁移 / 恢复

> **重要**：`dev-prepare.sh` / `dev-up.sh` / `dev-status.sh` / `dev-down.sh`（不带 `--purge`）**都不会删除数据**。
> 只有 `dev-down.sh --purge` 会删除 Docker 数据卷，且执行前会二次确认。

### 备份

```bash
# 备份 Postgres（新闻/任务/分析）+ Neo4j（知识图谱）
bash scripts/dev-backup.sh

# 连同 Milvus 向量数据一起备份（体积较大，向量其实可从新闻文本重新生成）
bash scripts/dev-backup.sh --with-milvus
```

备份产物在 `FinnewsHunter/.backups/<时间戳>/`（已加入 `.gitignore`，不会提交到仓库）。

### 迁移到新机器 / 新环境

```bash
# 旧机器：打包备份目录
tar czf finnews-backup.tar.gz .backups/20260705_143000/

# 新机器：解压后跑准备 + 启动，再恢复
scp finnews-backup.tar.gz newhost:~/FinnewsHunter/.backups/
cd FinnewsHunter
bash scripts/dev-prepare.sh
bash scripts/dev-up.sh
bash scripts/dev-restore.sh .backups/20260705_143000
```

### 恢复（覆盖当前数据）

```bash
# 交互式选择最近一次备份并恢复（会提示二次确认）
bash scripts/dev-restore.sh .backups/20260705_143000
```

### 数据分层说明（决定要不要备份）

| 存储 | 内容 | 是否关键 | 默认是否备份 |
|------|------|----------|--------------|
| Postgres | 新闻 / 爬取任务 / 分析结果 | ✅ 关键，无法重建 | ✅ 默认备份 |
| Neo4j | 知识图谱关系 | ✅ 关键 | ✅ 默认备份 |
| Milvus | 新闻文本的向量 embedding | ⚠️ 可从 Postgres 新闻重新跑 embedding 生成 | ❌ 默认跳过，`--with-milvus` 可选备份 |
| Redis | Celery 任务队列 / 缓存 | ❌ 纯队列，无需保留 | ❌ 不备份 |

### 彻底清空重来（危险操作）

```bash
# 停止容器 + 删除全部数据卷，需二次确认
bash scripts/dev-down.sh --purge
```

---

## 常见问题

### 「定向爬取任务已启动」但随后报 Celery worker 未启动

**原因**：只启动了 Postgres/Redis 等中间件，没有启动 Celery Worker。

**解决**：用 `bash scripts/dev-up.sh` 统一启动，或单独补：

```bash
docker compose -f deploy/docker-compose.dev.yml up -d celery-worker celery-beat
```

### 端口对照（本地 .env 连接 Docker 映射）

| 服务 | 容器内 | 宿主机（.env 填这个） |
|------|--------|----------------------|
| Postgres | 5432 | **5433** |
| Redis | 6379 | **6380** |
| Milvus | 19530 | 19530 |
| Neo4j Bolt | 7687 | 7687 |

### 查看 Celery 日志

```bash
docker logs -f finnews_celery_worker
docker logs -f finnews_celery_beat
```

### 查看本地 API / 前端日志

```bash
tail -f .runtime/logs/api.log
tail -f .runtime/logs/frontend.log
```

---

## 与旧文档的区别

旧 README 把启动拆成 6～8 步（中间件 docker 一次、Celery docker 又一次、API 本地、前端本地），容易漏掉 Celery。

**现在统一为**：
- `dev-prepare.sh` → 一次性准备
- `dev-up.sh` → 每次启动（Docker 全包 + 本地前后端）
- `dev-status.sh` / `dev-down.sh` → 运维
