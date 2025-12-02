#!/bin/bash
# Celery 一键启动脚本

set -e

echo "============================================"
echo "  FinnewsHunter Celery 启动脚本"
echo "============================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查是否已有 Celery 进程在运行
if pgrep -f "celery.*worker" > /dev/null; then
    echo "⚠️  检测到 Celery Worker 已在运行"
    read -p "是否杀掉旧进程并重启？(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在停止旧进程..."
        pkill -9 -f "celery.*worker" || true
        pkill -9 -f "celery.*beat" || true
        sleep 2
    else
        echo "❌ 已取消启动"
        exit 0
    fi
fi

# 检查 Redis 是否运行
echo ""
echo "[1/4] 检查 Redis 连接..."
if docker exec finnews_redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis 正常运行"
else
    echo "❌ Redis 未运行，请先启动 Docker Compose:"
    echo "   cd ../deploy && docker-compose -f docker-compose.dev.yml up -d redis"
    exit 1
fi

# 初始化数据库（确保 crawl_tasks 表存在）
echo ""
echo "[2/4] 初始化数据库..."
python init_db.py || echo "⚠️  数据库初始化失败（可能已存在）"

# 启动 Celery Worker
echo ""
echo "[3/4] 启动 Celery Worker..."
celery -A app.core.celery_app worker --loglevel=info --logfile=logs/celery_worker.log &
WORKER_PID=$!
echo "✅ Worker 已启动 (PID: $WORKER_PID)"

# 等待 Worker 启动
sleep 3

# 启动 Celery Beat
echo ""
echo "[4/4] 启动 Celery Beat..."
celery -A app.core.celery_app beat --loglevel=info --logfile=logs/celery_beat.log &
BEAT_PID=$!
echo "✅ Beat 已启动 (PID: $BEAT_PID)"

echo ""
echo "============================================"
echo "  ✨ Celery 启动成功！"
echo "============================================"
echo ""
echo "📋 进程信息:"
echo "   - Worker PID: $WORKER_PID"
echo "   - Beat PID: $BEAT_PID"
echo ""
echo "📝 日志文件:"
echo "   - Worker: logs/celery_worker.log"
echo "   - Beat: logs/celery_beat.log"
echo ""
echo "📊 监控命令:"
echo "   - 查看 Worker 日志: tail -f logs/celery_worker.log"
echo "   - 查看 Beat 日志: tail -f logs/celery_beat.log"
echo "   - 查看任务列表: curl http://localhost:8000/api/v1/tasks/"
echo ""
echo "⏱️  实时监控已启动，每5分钟自动爬取新闻"
echo ""
echo "🛑 停止服务:"
echo "   pkill -9 -f 'celery'"
echo ""
echo "============================================"

