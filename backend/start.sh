#!/bin/bash
# FinnewsHunter 启动脚本

set -e

echo "==================================="
echo "  FinnewsHunter Backend Startup"
echo "==================================="

# 获取脚本所在目录（backend目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/../deploy" && pwd)"

# 1. 启动 Docker Compose 服务
echo ""
echo "[1/4] Starting Docker Compose services..."
cd "$DEPLOY_DIR"
docker-compose -f docker-compose.dev.yml up -d

# 等待数据库启动
echo ""
echo "[2/4] Waiting for databases to be ready..."
sleep 10

# 2. 初始化数据库（首次运行）
echo ""
echo "[3/4] Initializing database..."
cd "$SCRIPT_DIR"
python init_db.py || echo "Database initialization skipped (may already exist)"

# 3. 启动 FastAPI 应用
echo ""
echo "[4/4] Starting FastAPI application..."
echo ""
echo "🚀 Server will start at: http://localhost:8000"
echo "📚 API Documentation: http://localhost:8000/docs"
echo ""

# 确保在 backend 目录下启动
cd "$SCRIPT_DIR"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

