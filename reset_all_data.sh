#!/bin/bash
# 一键清空所有数据并重新开始爬取

set -e

echo "=========================================="
echo "  FinnewsHunter 数据重置脚本"
echo "=========================================="
echo ""
echo "⚠️  警告：此操作将删除所有新闻和任务数据！"
echo "⚠️  此操作不可恢复！"
echo ""
read -p "确认要清空所有数据吗？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ 操作已取消"
    exit 0
fi

echo ""
echo "开始清空数据..."
echo ""

# 1. 清空PostgreSQL数据
echo "[1/4] 清空PostgreSQL数据..."
docker exec finnews_postgres psql -U finnews -d finnews_db <<EOF
-- 清空新闻表
DELETE FROM news;
-- 清空任务表
DELETE FROM crawl_tasks;
-- 清空分析表（如果存在）
DELETE FROM analyses;
-- 重置自增ID
ALTER SEQUENCE news_id_seq RESTART WITH 1;
ALTER SEQUENCE crawl_tasks_id_seq RESTART WITH 1;
ALTER SEQUENCE analyses_id_seq RESTART WITH 1;
-- 显示结果
SELECT 'news表', COUNT(*) FROM news;
SELECT 'crawl_tasks表', COUNT(*) FROM crawl_tasks;
EOF

echo "✅ PostgreSQL数据已清空"
echo ""

# 2. 清空Redis缓存
echo "[2/4] 清空Redis缓存..."
docker exec finnews_redis redis-cli FLUSHDB
echo "✅ Redis缓存已清空"
echo ""

# 3. 清空Celery调度文件
echo "[3/4] 清空Celery调度文件..."
rm -f backend/celerybeat-schedule
rm -rf backend/celerybeat-schedule.db
echo "✅ Celery调度文件已清空"
echo ""

# 4. 重启所有服务
echo "[4/4] 重启服务..."
cd "$(dirname "$0")"
docker compose -f deploy/docker-compose.dev.yml restart celery-worker celery-beat

echo ""
echo "=========================================="
echo "  ✨ 数据重置完成！"
echo "=========================================="
echo ""
echo "📋 状态："
echo "  - PostgreSQL: 已清空"
echo "  - Redis: 已清空"
echo "  - Celery: 已重启"
echo ""
echo "🚀 下一步："
echo "  1. Celery Beat 每1分钟会自动爬取10个新闻源"
echo "  2. 约5-10分钟后可在前端查看新数据"
echo "  3. 访问 http://localhost:3000 查看进度"
echo ""
echo "=========================================="

