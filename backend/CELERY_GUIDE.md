# Celery 实时监控使用指南

## 📋 功能说明

Phase 1.5 已实现自动化数据采集功能，支持：
- ⚡ **实时监控**：每5分钟自动爬取最新新闻
- 🥶 **冷启动**：批量回溯历史数据（1-100页）
- 📊 **任务追踪**：实时查看任务进度和统计

---

## 🚀 快速启动

### 1. 初始化数据库（添加 crawl_tasks 表）

```bash
cd backend
python init_db.py
```

### 2. 启动 Redis（如果还没启动）

```bash
# 检查 Docker Compose 中的 Redis 是否运行
docker ps | grep redis

# 或者直接启动所有服务
cd ../deploy
docker-compose -f docker-compose.dev.yml up -d
```

### 3. 启动 Celery Worker（处理任务）

```bash
# Terminal 1: 启动 Worker
cd backend
celery -A app.core.celery_app worker --loglevel=info
```

### 4. 启动 Celery Beat（定时调度）

```bash
# Terminal 2: 启动 Beat（调度器）
cd backend
celery -A app.core.celery_app beat --loglevel=info
```

### 5. 启动 FastAPI 后端

```bash
# Terminal 3: 启动后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📡 API 使用说明

### 1. 查看任务列表

```bash
# 查看所有任务
curl http://localhost:8000/api/v1/tasks/

# 按模式筛选（realtime, cold_start）
curl http://localhost:8000/api/v1/tasks/?mode=realtime

# 按状态筛选（pending, running, completed, failed）
curl http://localhost:8000/api/v1/tasks/?status=completed

# 分页
curl http://localhost:8000/api/v1/tasks/?skip=0&limit=10
```

### 2. 查看任务详情

```bash
curl http://localhost:8000/api/v1/tasks/1
```

响应示例：
```json
{
  "id": 1,
  "celery_task_id": "3a8d2b1c-4f5e-6a7b-8c9d-0e1f2a3b4c5d",
  "mode": "realtime",
  "status": "completed",
  "source": "sina",
  "progress": {"current_page": 1, "total_pages": 1, "percentage": 100},
  "crawled_count": 25,
  "saved_count": 8,
  "execution_time": 12.34,
  "result": {
    "total_crawled": 50,
    "filtered": 25,
    "saved": 8,
    "duplicates": 17
  },
  "created_at": "2025-12-01T14:30:00",
  "completed_at": "2025-12-01T14:30:12"
}
```

### 3. 触发冷启动（批量爬取）

```bash
# 爬取新浪财经 1-50 页
curl -X POST http://localhost:8000/api/v1/tasks/cold-start \
  -H "Content-Type: application/json" \
  -d '{
    "source": "sina",
    "start_page": 1,
    "end_page": 50
  }'
```

响应：
```json
{
  "success": true,
  "message": "冷启动任务已启动: sina, 页码 1-50",
  "celery_task_id": "abc123..."
}
```

### 4. 查看任务统计

```bash
curl http://localhost:8000/api/v1/tasks/stats/summary
```

响应：
```json
{
  "total": 120,
  "by_status": {
    "completed": 115,
    "running": 2,
    "failed": 3
  },
  "by_mode": {
    "realtime": 100,
    "cold_start": 20
  },
  "recent_completed": 45,
  "total_news_crawled": 5000,
  "total_news_saved": 3200
}
```

---

## 🔍 监控和调试

### 1. 查看 Celery Worker 日志

```bash
# Worker 日志会实时显示任务执行情况
[2025-12-01 14:30:00] Task app.tasks.crawl_tasks.realtime_crawl_task[abc123] received
[2025-12-01 14:30:01] [Task 15] 开始实时爬取: sina
[2025-12-01 14:30:10] [Task 15] 爬取到 50 条新闻
[2025-12-01 14:30:10] [Task 15] 过滤后剩余 25 条新闻
[2025-12-01 14:30:12] [Task 15] 完成! 爬取: 50, 过滤: 25, 保存: 8, 耗时: 11.23s
[2025-12-01 14:30:12] Task app.tasks.crawl_tasks.realtime_crawl_task[abc123] succeeded
```

### 2. 查看 Celery Beat 调度日志

```bash
# Beat 日志会显示定时任务触发
[2025-12-01 14:30:00] Scheduler: Sending due task crawl-sina-every-5min
[2025-12-01 14:35:00] Scheduler: Sending due task crawl-sina-every-5min
```

### 3. 监控 Redis 队列

```bash
# 查看队列长度
docker exec finnews_redis redis-cli LLEN celery

# 查看队列内容
docker exec finnews_redis redis-cli LRANGE celery 0 -1
```

### 4. 查看数据库中的任务

```bash
# 进入 PostgreSQL
docker exec -it finnews_postgres psql -U finnews -d finnews_db

# 查询任务
SELECT id, mode, status, source, crawled_count, saved_count, created_at 
FROM crawl_tasks 
ORDER BY created_at DESC 
LIMIT 10;
```

---

## ⚙️ 配置说明

### 修改定时任务频率

编辑 `backend/app/core/celery_app.py`:

```python
beat_schedule={
    "crawl-sina-every-5min": {
        "task": "app.tasks.crawl_tasks.realtime_crawl_task",
        "schedule": crontab(minute="*/5"),  # ← 改这里
        "args": ("sina",),
    },
}
```

频率选项：
- `crontab(minute="*/1")` - 每1分钟
- `crontab(minute="*/5")` - 每5分钟
- `crontab(minute="*/15")` - 每15分钟
- `crontab(hour="*/1")` - 每小时
- `crontab(minute=0, hour="*/2")` - 每2小时整点

### 添加新的新闻源

1. 创建爬虫工具（如 `jrj_crawler.py`）
2. 在 `crawl_tasks.py` 中添加支持
3. 在 `celery_app.py` 中添加定时任务

---

## 🎯 使用场景

### 场景 1: 首次启动（冷启动）

```bash
# 1. 启动所有服务
cd backend
celery -A app.core.celery_app worker &
celery -A app.core.celery_app beat &
uvicorn app.main:app &

# 2. 触发冷启动，回溯 30 页历史数据
curl -X POST http://localhost:8000/api/v1/tasks/cold-start \
  -H "Content-Type: application/json" \
  -d '{"source":"sina","start_page":1,"end_page":30}'

# 3. 等待约 20-30 分钟，查看进度
watch -n 5 'curl -s http://localhost:8000/api/v1/tasks/1'

# 4. 完成后，实时监控自动接管（每5分钟）
```

### 场景 2: 日常运行（实时监控）

```bash
# 保持 Worker 和 Beat 运行
# 系统会每5分钟自动爬取最新新闻
# 无需手动干预

# 查看今天采集了多少新闻
curl http://localhost:8000/api/v1/news/?limit=100

# 查看实时监控任务统计
curl http://localhost:8000/api/v1/tasks/?mode=realtime&limit=20
```

### 场景 3: 补充历史数据

```bash
# 发现某天数据缺失，补充爬取
curl -X POST http://localhost:8000/api/v1/tasks/cold-start \
  -H "Content-Type: application/json" \
  -d '{"source":"sina","start_page":10,"end_page":20}'
```

---

## 🐛 常见问题

### Q1: Worker 启动失败

**错误**: `Connection refused` 或 `Error 111`

**解决**:
```bash
# 检查 Redis 是否运行
docker ps | grep redis

# 检查 Redis 连接
docker exec finnews_redis redis-cli ping
# 应该返回 PONG

# 检查 .env 中的 REDIS_HOST 配置
grep REDIS_HOST .env
```

### Q2: 定时任务不执行

**解决**:
```bash
# 1. 确认 Beat 正在运行
ps aux | grep "celery.*beat"

# 2. 查看 Beat 日志
celery -A app.core.celery_app beat --loglevel=debug

# 3. 检查系统时间
date
# 应该与服务器时间一致
```

### Q3: 任务卡在 PENDING 状态

**解决**:
```bash
# 1. 检查 Worker 是否运行
ps aux | grep "celery.*worker"

# 2. 重启 Worker
pkill -9 celery
celery -A app.core.celery_app worker --loglevel=info

# 3. 清理 Redis 队列（谨慎使用）
docker exec finnews_redis redis-cli FLUSHALL
```

### Q4: 爬取到的新闻数为 0

**可能原因**:
1. 新闻源网站结构变化（需要更新爬虫）
2. 被反爬封禁（IP/User-Agent）
3. 时间过滤太严格（实时监控只保留1小时内的）

**调试**:
```bash
# 查看任务详情
curl http://localhost:8000/api/v1/tasks/{task_id}

# 查看 Worker 日志中的错误信息

# 手动测试爬虫
cd backend
python -c "
from app.tools import SinaCrawlerTool
crawler = SinaCrawlerTool()
news = crawler.crawl(1, 1)
print(f'爬取到 {len(news)} 条新闻')
"
```

---

## 🎉 验收检查

✅ **系统正常运行的标志**:

1. **Worker 运行中**
```bash
ps aux | grep "celery.*worker"
# 应该看到进程
```

2. **Beat 调度正常**
```bash
curl http://localhost:8000/api/v1/tasks/ | jq '.[0].mode'
# 应该定期出现 "realtime" 任务
```

3. **任务成功率 > 95%**
```bash
curl http://localhost:8000/api/v1/tasks/stats/summary | jq
# by_status.completed / total > 0.95
```

4. **新闻持续增长**
```bash
curl http://localhost:8000/api/v1/news/?limit=1 | jq '.[0].created_at'
# 应该是最近5-10分钟内的
```

---

## 📚 相关文档

- [CRAWL_STRATEGY.md](../CRAWL_STRATEGY.md) - 完整爬取策略设计
- [planning.md](../../planning.md) - 项目整体规划
- [Celery 官方文档](https://docs.celeryq.dev/)

---

**🎊 Phase 1.5 完成！系统现在可以自动积累数据了！**

